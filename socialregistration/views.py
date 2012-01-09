import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.template import RequestContext
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect

try:
    from django.views.decorators.csrf import csrf_protect
    has_csrf = True
except ImportError:
    has_csrf = False

from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout as auth_logout
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site

from socialregistration.forms import UserForm, ClaimForm, ExistingUser
from socialregistration.utils import (OAuthClient, OAuthTwitter,
    OpenID, _https, DiscoveryFailure)
from socialregistration.models import FacebookProfile, TwitterProfile, OpenIDProfile


FB_ERROR = _('We couldn\'t validate your Facebook credentials')

GENERATE_USERNAME = bool(getattr(settings, 'SOCIALREGISTRATION_GENERATE_USERNAME', False))

logger = logging.getLogger(getattr(settings, 'SOCIALREGISTRATION_LOGGER_NAME', 'socialregistration'))


def post_disconnect_redirect_url(instance, request=None):
    # first check to see if the object has a URL
    try:
        return instance.get_absolute_url()
    except AttributeError:
        pass
    # then their session
    if request:
        if 'SOCIALREGISTRATION_DISCONNECT_URL' in request.session:
            return request.session['SOCIALREGISTRATION_DISCONNECT_URL']
    # fall back to the setting, if it exists
    url = getattr(settings, 'SOCIALREGISTRATION_DISCONNECT_URL', '')
    if url:
        return url
    else:
        # no clue - go to the root URL I guess
        return '/'

def disconnect(request, network, object_type, object_id):
    profile_model = ContentType.objects.get(pk=network).model_class() # retrieve the model of the network profile
    profile = profile_model.objects.get(content_type__id=object_type, object_id=object_id)
    model = ContentType.objects.get(pk=object_type).model_class()
    content_object = model.objects.get(pk=object_id)

    if request.method == 'POST':
        logger.info("Disconnecting %s social profile %s because the user requested it. They will be redirected to %s." % (profile_model, object_id, post_disconnect_redirect_url(content_object)))
        profile.delete()
        return HttpResponseRedirect(post_disconnect_redirect_url(content_object))
    else:
        return render_to_response('socialregistration/confirm_disconnect.html', {
            'profile': profile,
            'instance': content_object,
        }, context_instance=RequestContext(request))

def _get_next(request):
    """
    Returns a url to redirect to after the login
    """
    if 'next' in request.session:
        next = request.session['next']
        del request.session['next']
        return next
    elif 'next' in request.GET:
        return request.GET.get('next')
    elif 'next' in request.POST:
        return request.POST.get('next')
    else:
        return getattr(settings, 'LOGIN_REDIRECT_URL', '/')

def _authenticate_login_redirect(request):
    """
    Authenticates user, clears unneeded session variables, and redirects them.
    """
    user = request.session['socialregistration_profile'].authenticate()
    login(request, user)
    if 'socialregistration_user' in request.session: del request.session['socialregistration_user']
    if 'socialregistration_profile' in request.session: del request.session['socialregistration_profile']
    return HttpResponseRedirect(_get_next(request))

def setup(request, template='socialregistration/setup.html',
    form_class=UserForm, extra_context=dict(), claim_form_class=ClaimForm):
    """
    Setup view to create a username & set email address after authentication
    """
    try:
        social_user = request.session['socialregistration_user']
        social_profile = request.session['socialregistration_profile']
    except KeyError:
        logger.error("A KeyError was encountered while setting up a socialregistration account. Session was: %s" % request.session)
        return render_to_response(
            template, dict(error=True), context_instance=RequestContext(request))

    # The following associates the correct existing user if they have logged
    # in via a different site on the same database. It allows them to skip the
    # setup process because they have done this before on a different site,
    # therefore they have a password-less user that would be impossible to
    # associate using the ClaimForm.
    profile_model = social_profile.__class__
    existing_profiles = profile_model.objects.filter(**{profile_model.remote_id_field: social_profile.remote_id})
    logger.debug("Found %s existing profiles with criteria %s = %s" % (existing_profiles.count, profile_model.remote_id_field, social_profile.remote_id))
    if existing_profiles:
        logger.info("Found a matching profile, will link profile %s to the same content object as %s" % (social_profile.pk, existing_profiles[0].pk))
        existing_profile = existing_profiles[0]
        social_profile.content_object = existing_profile.content_object
        social_profile.save()
        logger.info("Linked. Redirecting the request.")
        return _authenticate_login_redirect(request)

    if not GENERATE_USERNAME:
        # User can pick own username
        if not request.method == "POST":
            logger.debug("Setting up a new profile, username not provided yet.")
            form = form_class(social_user, social_profile,)
        else:
            logger.debug("Setting up a new social network profile, provided form data: %s" % request.POST)
            form = form_class(social_user, social_profile, request.POST)
            try:
                if form.is_valid():
                    form.save()
                    user = form.profile.authenticate()
                    user.set_unusable_password() # we want something there, but it doesn't need to be anything they can actually use - otherwise a password must be assigned manually before the user can be banned or any other administrative action can be taken
                    user.save()
                    return _authenticate_login_redirect(request)

            except ExistingUser:
                logger.debug("The user's requested username exists already.")
                # see what the error is. if it's just an existing user, we want to let them claim it.
                if 'submitted' in request.POST:
                    form = claim_form_class(
                        request.session['socialregistration_user'],
                        request.session['socialregistration_profile'],
                        request.POST
                    )
                else:
                    form = claim_form_class(
                        request.session['socialregistration_user'],
                        request.session['socialregistration_profile'],
                        initial=request.POST
                    )

                if form.is_valid():
                    logger.debug("The existing user successfully authenticated and their social network credentials are being extended to their existing user account.")
                    form.save()

                    return _authenticate_login_redirect(request)

                extra_context['claim_account'] = True

        extra_context.update(dict(form=form))

        return render_to_response(template, extra_context,
            context_instance=RequestContext(request))

    else:
        # Generate user and profile
        social_user.username = str(uuid.uuid4())[:30]
        social_user.save()
        social_user.set_unusable_password() # we want something there, but it doesn't need to be anything they can actually use - otherwise a password must be assigned manually before the user can be banned or any other administrative action can be taken
        social_user.save()

        social_profile.content_object = social_user
        social_profile.save()

        logger.debug("Username was autogenerated as %s; unusable password set and account connected." % social_user.username)

        return _authenticate_login_redirect(request)

if has_csrf:
    setup = csrf_protect(setup)

def facebook_login(request, template='socialregistration/facebook.html',
    extra_context=dict(), account_inactive_template='socialregistration/account_inactive.html'):
    """
    View to handle the Facebook login
    """
    if request.facebook.uid is None:
        logger.info("No Facebook UID was received, notifying user of error.")
        extra_context.update(dict(error=FB_ERROR))
        return render_to_response(template, extra_context,
            context_instance=RequestContext(request))

    user = authenticate(uid=request.facebook.uid)

    if user is None:
        logger.info("Unable to find a user match for Facebook UID %s, redirecting to have them set up an account." % request.facebook.uid)
        request.session['socialregistration_user'] = User()
        request.session['socialregistration_profile'] = FacebookProfile(uid=request.facebook.uid)
        request.session['next'] = _get_next(request)
        return HttpResponseRedirect(reverse('socialregistration_setup'))

    if not user.is_active:
        logger.info("Found a match for the user's Facebook UID (%s), but the account is inactive. Alerting the user of this." % request.facebook.uid)
        return render_to_response(account_inactive_template, extra_context,
            context_instance=RequestContext(request))

    login(request, user)

    return HttpResponseRedirect(_get_next(request))

def facebook_connect(request, template='socialregistration/facebook.html',
    extra_context=dict()):
    """
    View to handle connecting existing django accounts with facebook
    """
    # for facebook the login is done in JS, so by the time it hits our view here there is no redirect step. Look for the querystring values and use that instead of worrying about session.
    connect_object = get_object(request.GET)
    logger.debug("The object to be connected to is %s" % connect_object)

    if getattr(request.facebook, 'user', False): # only go this far if the user authorized our application and there is user info
        if connect_object:
            # this exists so that social credentials can be attached to any arbitrary object using the same callbacks.
            # Under normal circumstances it will not be used. Put an object in request.session named 'socialregistration_connect_object' and it will be used instead.
            # After the connection is made it will redirect to request.session value 'socialregistration_connect_redirect' or settings.LOGIN_REDIRECT_URL or /
            try:
                # get the profile for this facebook UID and connected object
                profile = FacebookProfile.objects.get(uid=request.facebook.uid, content_type=ContentType.objects.get_for_model(connect_object.__class__), object_id=connect_object.pk)
                profile.consumer_key = request.facebook.user['access_token']
                profile.secret = request.facebook.user['secret']
                profile.save()
                logger.info("Found and updated consumer key (%s) / secret (%s) for Facebook Profile of object %s" % (request.facebook.user['access_token'], request.facebook.user['secret'], connect_object))
            except FacebookProfile.DoesNotExist:
                logger.info("No Facebook Profile found. Creating Facebook Profile for %s. Facebook UID is %s, consumer key %s and secret %s" % (connect_object, request.facebook.uid, request.facebook.user['access_token'], request.facebook.user['secret']))
                FacebookProfile.objects.create(content_object=connect_object, uid=request.facebook.uid, \
                    consumer_key=request.facebook.user['access_token'], consumer_secret=request.facebook.user['secret'])
        else:
            logger.debug("No connect object was specified, so we're linking to the currently logged in user.")
            if request.facebook.uid is None or request.user.is_authenticated() is False:
                extra_context.update(dict(error=FB_ERROR))
                logger.info("Returned Facebook UID %s, user auth status %s" % (request.facebook.uid, request.user.is_authenticated()))
                logger.info("Facebook Error occurred, alerting the user.")
                return render_to_response(template, extra_context,
                    context_instance=RequestContext(request))

            try:
                profile = FacebookProfile.objects.get(uid=request.facebook.uid, content_type=ContentType.objects.get_for_model(User))
                profile.consumer_key = request.facebook.user['access_token']
                profile.secret = request.facebook.user['secret']
                profile.save()
                logger.info("Found and updated consumer key (%s) / secret (%s) for Facebook Profile of user %s" % (request.facebook.user['access_token'], request.facebook.user['secret'], request.user))
            except FacebookProfile.DoesNotExist:
                logger.info("No Facebook Profile found. Creating Facebook Profile for %s. Facebook UID is %s, consumer key %s and secret %s" % (request.user, request.facebook.uid, request.facebook.user['access_token'], request.facebook.user['secret']))
                profile = FacebookProfile.objects.create(content_object=request.user,
                    uid=request.facebook.uid, consumer_key=request.facebook.user['access_token'], consumer_secret=request.facebook.user['secret'])
    else:
        logger.info("The user did not authorize connecting Facebook.")
        messages.info(request, "You must authorize the Facebook application in order to link your account.")
        try:
            redirect = request.META['HTTP_REFERER']  # send them where they came from
        except KeyError:
            redirect = _get_next(request)  # and fall back to what the view would use otherwise
        logger.info("Redirecting the user to %s after they didn't authorize Facebook connections." % redirect)
        return HttpResponseRedirect(redirect)

    logger.info("Falling back on a redirection to %s" % _get_next(request))
    return HttpResponseRedirect(_get_next(request))

def logout(request, redirect_url=None):
    """
    Logs the user out of django. This is only a wrapper around
    django.contrib.auth.logout. Logging users out of Facebook for instance
    should be done like described in the developer wiki on facebook.
    http://wiki.developers.facebook.com/index.php/Connect/Authorization_Websites#Logging_Out_Users
    """
    logger.info("User %s requested to be logged out." % request.user)
    auth_logout(request)

    url = redirect_url or getattr(settings, 'LOGOUT_REDIRECT_URL', '/')
    logger.debug("Requesting now-logged-out user to %s" % url)

    return HttpResponseRedirect(url)

def twitter(request, account_inactive_template='socialregistration/account_inactive.html',
    extra_context=dict()):
    """
    Actually setup/login an account relating to a twitter user after the oauth
    process is finished successfully
    """

    client = OAuthTwitter(
        request, settings.TWITTER_CONSUMER_KEY,
        settings.TWITTER_CONSUMER_SECRET_KEY,
        settings.TWITTER_REQUEST_TOKEN_URL,
    )

    user_info = client.get_user_info()
    logger.debug("User info known about user from Twitter: %s" % user_info)

    try:
        oauth_token = request.session['oauth_api.twitter.com_access_token']['oauth_token']
    except KeyError:
        try:
            oauth_token = request.session['oauth_twitter.com_access_token']['oauth_token']
        except:
            oauth_token = ''
    try:
        oauth_token_secret = request.session['oauth_api.twitter.com_access_token']['oauth_token_secret']
    except KeyError:
        try:
            oauth_token_secret = request.session['oauth_twitter.com_access_token']['oauth_token_secret']
        except:
            oauth_token_secret = ''

    logger.debug("Received token: %s / Secret: %s" % (oauth_token, oauth_token_secret))

    if 'socialregistration_connect_object' in request.session and request.session['socialregistration_connect_object'] != None:
        logger.debug("Object to be connected to: %s" % request.session['socialregistration_connect_object'])
        # this exists so that social credentials can be attached to any arbitrary object using the same callbacks.
        # Under normal circumstances it will not be used. Put an object in request.session named 'socialregistration_connect_object' and it will be used instead.
        # After the connection is made it will redirect to request.session value 'socialregistration_connect_redirect' or settings.LOGIN_REDIRECT_URL or /
        try:
            # get the profile for this Twitter ID and type of connected object
            profile = TwitterProfile.objects.get(twitter_id=user_info['id'], content_type=ContentType.objects.get_for_model(request.session['socialregistration_connect_object'].__class__), object_id=request.session['socialregistration_connect_object'].pk)
            logger.debug("Found Twitter Profile for %s, Twitter User ID %s" % (request.session['socialregistration_connect_object'], user_info['id']))
        except TwitterProfile.DoesNotExist:
            TwitterProfile.objects.create(content_object=request.session['socialregistration_connect_object'], twitter_id=user_info['id'], \
                screenname=user_info['screen_name'], consumer_key=oauth_token, consumer_secret=oauth_token_secret)
            logger.debug("Created Twitter Profile for %s, Twitter User ID %s / screen name %s" % (request.session['socialregistration_connect_object'], user_info['id'], user_info['screen_name']))

        del request.session['socialregistration_connect_object']
    else:
        logger.debug("No connection object found, will use currently logged in user instead.")
        if request.user.is_authenticated():
            # Handling already logged in users connecting their accounts
            try:
                profile = TwitterProfile.objects.get(twitter_id=user_info['id'], content_type=ContentType.objects.get_for_model(User))
            except TwitterProfile.DoesNotExist:  # There can only be one profile!
                profile = TwitterProfile.objects.create(content_object=request.user, twitter_id=user_info['id'], screenname=user_info['screen_name'], consumer_key=oauth_token, consumer_secret=oauth_token_secret)

            logger.debug("Redirecting user to %s after matching up a Twitter Profile." % _get_next(request))
            return HttpResponseRedirect(_get_next(request))

        user = authenticate(twitter_id=user_info['id'])

        if user is None:
            request.session['socialregistration_profile'] = TwitterProfile(twitter_id=user_info['id'], screenname=user_info['screen_name'], consumer_key=oauth_token, consumer_secret=oauth_token_secret)
            request.session['socialregistration_user'] = User()
            request.session['next'] = _get_next(request)
            logger.info("No user found / authentication failed for Twitter ID %s, sending to %s to login, will send to %s after login." % (user_info['id'], reverse('socialregistration_setup'), request.session['next']))
            return HttpResponseRedirect(reverse('socialregistration_setup'))

        if not user.is_active:
            logger.info("The user logging in is marked inactive. Alerting them to this.")
            return render_to_response(
                account_inactive_template,
                extra_context,
                context_instance=RequestContext(request)
            )

        login(request, user)

    logger.info("Falling back, redirecting user to %s" % _get_next(request))
    return HttpResponseRedirect(_get_next(request))

def get_object(info):
    if 'a' and 'm' in info:
        model = ContentType.objects.get_by_natural_key(app_label=info['a'], model=info['m']).model_class()
        return model.objects.get(pk=info['i'])
    return None

def oauth_redirect(request, consumer_key=None, secret_key=None,
    request_token_url=None, access_token_url=None, authorization_url=None,
    callback_url=None, parameters=None):
    """
    View to handle the OAuth based authentication redirect to the service provider
    """
    request.session['socialregistration_connect_object'] = get_object(request.GET)

    request.session['next'] = _get_next(request)
    client = OAuthClient(request, consumer_key, secret_key,
        request_token_url, access_token_url, authorization_url, callback_url, parameters)
    logger.debug("Processing oAuth redirect.")
    return client.get_redirect()

def oauth_callback(request, consumer_key=None, secret_key=None,
    request_token_url=None, access_token_url=None, authorization_url=None,
    callback_url=None, template='socialregistration/oauthcallback.html',
    extra_context=dict(), parameters=None):
    """
    View to handle final steps of OAuth based authentication where the user
    gets redirected back to from the service provider
    """
    client = OAuthClient(request, consumer_key, secret_key, request_token_url,
        access_token_url, authorization_url, callback_url, parameters)

    # the user has denied us - throw that in messages to be displayed and send them back where they came from
    if 'denied' in request.GET:
        logger.debug("The user denied access via oAuth.")
        messages.info(request, "You must authorize the application in order to link your account.")
        try:
            redirect = request.META['HTTP_REFERER']  # send them where they came from
        except KeyError:
            redirect = _get_next(request)  # and fall back to what the view would use otherwise
        logger.debug("Redirecting user to %s" % redirect)
        return HttpResponseRedirect(redirect)

    extra_context.update(dict(oauth_client=client))

    if not client.is_valid():
        logger.info("The oAuth client was invalid, rendering callback template.")
        return render_to_response(
            template, extra_context, context_instance=RequestContext(request)
        )

    # We're redirecting to the setup view for this oauth service
    logger.info("Everything looks good, sending user to the setup view at %s" % reverse(client.callback_url))
    return HttpResponseRedirect(reverse(client.callback_url))

def openid_redirect(request):
    """
    Redirect the user to the openid provider
    """
    request.session['next'] = _get_next(request)
    request.session['openid_provider'] = request.GET.get('openid_provider')
    request.session['socialregistration_connect_object'] = get_object(request.GET)

    client = OpenID(
        request,
        'http%s://%s%s' % (
            _https(),
            Site.objects.get_current().domain,
            reverse('openid_callback')
        ),
        request.GET.get('openid_provider')
    )
    try:
        logger.info("Received redirect to %s from OpenID" % client.get_redirect())
        return client.get_redirect()
    except DiscoveryFailure:
        request.session['openid_error'] = True
        logger.info("OpenID failure, sending user to login.")
        return HttpResponseRedirect(settings.LOGIN_URL)

def openid_callback(request, template='socialregistration/openid.html',
    extra_context=dict(), account_inactive_template='socialregistration/account_inactive.html'):
    """
    Catches the user when he's redirected back from the provider to our site
    """
    client = OpenID(
        request,
        'http%s://%s%s' % (
            _https(),
            Site.objects.get_current().domain,
            reverse('openid_callback')
        ),
        request.session.get('openid_provider')
    )

    if client.is_valid():
        logger.info("OpenID login succeeded.")
        identity = client.result.identity_url

        if 'socialregistration_connect_object' in request.session and request.session['socialregistration_connect_object'] != None:
            # this exists so that social credentials can be attached to any arbitrary object using the same callbacks.
            # Under normal circumstances it will not be used. Put an object in request.session named 'socialregistration_connect_object' and it will be used instead.
            # After the connection is made it will redirect to request.session value 'socialregistration_connect_redirect' or settings.LOGIN_REDIRECT_URL or /
            logger.info("Will be connecting these credentials to %s" % request.session['socialregistration_connect_object'])
            try:
                # get the profile for this facebook UID and type of connected object
                profile = OpenIDProfile.objects.get(identity=identity, content_type=ContentType.objects.get_for_model(request.session['socialregistration_connect_object'].__class__), object_id=request.session['socialregistration_connect_object'].pk)
            except OpenIDProfile.DoesNotExist:
                OpenIDProfile.objects.create(content_object=request.session['socialregistration_connect_object'], identity=identity)

            logger.debug("OpenID profile updated for object.")

            del request.session['socialregistration_connect_object']
        else:
            logger.info("Will be connecting these credentials to the currently logged in user, %s" % request.user)
            if request.user.is_authenticated():
                # Handling already logged in users just connecting their accounts
                try:
                    profile = OpenIDProfile.objects.get(identity=identity, content_type=ContentType.objects.get_for_model(User))
                except OpenIDProfile.DoesNotExist: # There can only be one profile with the same identity
                    profile = OpenIDProfile.objects.create(content_object=request.user,
                        identity=identity)

                logger.info("Connected OpenID profile, sending them on to %s" % _get_next(request))
                return HttpResponseRedirect(_get_next(request))

            user = authenticate(identity=identity)
            if user is None:
                request.session['socialregistration_user'] = User()
                request.session['socialregistration_profile'] = OpenIDProfile(
                    identity=identity
                )
                logger.info("We don't know who this OpenID user is. Sending them to the setup view.")
                return HttpResponseRedirect(reverse('socialregistration_setup'))

            if not user.is_active:
                logger.info("User attemping to connect OpenID credentials is not active.")
                return render_to_response(
                    account_inactive_template,
                    extra_context,
                    context_instance=RequestContext(request)
                )

            login(request, user)
            logger.debug("User has been logged in, sending them to %s." % _get_next(request))
        return HttpResponseRedirect(_get_next(request))

    logger.debug("Falling back to default OpenID template.")
    return render_to_response(
        template,
        dict(),
        context_instance=RequestContext(request)
    )
