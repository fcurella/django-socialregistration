==========================
Django Social Registration
==========================

Django Social Registration enables developers to add alternative registration
methods based on third party sites.


Requirements
============
- django_
- oauth2_
- python-openid_
- python-sdk_

Installation
============

#. Add the ``socialregistration`` directory to your ``PYTHON_PATH``.
#. Add ``socialregistration`` to your ``INSTALLED_APPS`` settings of Django.
#. Add ``socialregistration.urls`` to your ``urls.py`` file.

Backwards Incompatibility
=========================

A necessary backwards-incompatible change was made 9/16/2010 to use Generic ForeignKeys instead of a direct tie to users. This change
makes socialregistration more about authentication / linking of social accounts to any object (organizations, users, groups, etc.)
The migration 0003_add_generic_relation_fields will add the necessary fields (object_id and content_type) 
0004_migrate_existing_profiles will take all profiles created for your users and "convert" them to use Generic ForeignKeys
instead. Another migration 0005_remove_user_tie will drop the "user" column.

Configuration
=============

Facebook Connect
----------------
#. Set up a Facebook application at http://www.facebook.com/developers/

   * Set up new app
   * Name and agree to their terms
   * Under "Web Site" set your site URL (main) and domain.
   * Grab "App ID" (FACEBOOK_API_KEY) and "App Secret" (FACEBOOK_SECRET_KEY)

#. Add ``FACEBOOK_API_KEY`` and ``FACEBOOK_SECRET_KEY`` to your settings file representing the keys you were given by Facebook.
#. Add ``socialregistration.auth.FacebookAuth`` to ``AUTHENTICATION_BACKENDS`` in your settings file.
#. Add ``socialregistration.middleware.FacebookMiddleware`` to ``MIDDLEWARE_CLASSES`` in your settings file.
#.  Add tags to your template file::

    {% load facebook_tags %}
    {% facebook_button %}
    {% facebook_js %}

Twitter
-------
#. Set up a Twitter application at http://dev.twitter.com/apps/

   * Register a new app
   * Name, describe, and set other fields.
   * Callback URL will be your site's url + /socialregistration/twitter/callback/ unless you set up your URLconf differently than the test projects.
   * Choose Read/Write or Read only wisely - it's better to only ask for what you need but you can't go from read-only to read/write later without user approval.
   * Grab "Consumer Key" (TWITTER_CONSUMER_KEY) and "Consumer Secret" (TWITTER_CONSUMER_SECRET_KEY)

#. Add the following variables to your ``settings.py`` file with the values you were given by Twitter::

    TWITTER_CONSUMER_KEY
    TWITTER_CONSUMER_SECRET_KEY
    TWITTER_REQUEST_TOKEN_URL
    TWITTER_ACCESS_TOKEN_URL
    TWITTER_AUTHORIZATION_URL

#. Add ``socialregistration.auth.TwitterAuth`` to your ``AUTHENTICATION_BACKENDS`` settings.

#. Add tags to your template file::

    {% load twitter_tags %}
    {% twitter_button %}


Other OAuth Services
--------------------
Please refer to the Twitter implementation of the signup / login process to
extend your own application to act as a consumer of other OAuth providers.
Basically it's just plugging together some urls and creating an auth backend,
a model and a view.


OpenID
------
#. Add ``socialregistration.auth.OpenIDAuth`` to ``AUTHENTICATION_BACKENDS`` in your settings.
#. Add tags to your template file::

    {% load openid_tags %}
    {% openid_form %}

Logging users out
-----------------
You can use the standard {% url auth_logout %} url to log users out of Django.
Please note that this will not log users out of third party sites though. Logging out a 
Facebook user might look something like this:: 

    <a href="#" onclick="javascript:FB.logout(function(response){ document.location = '{% url auth_logout %}' })">Logout</a>

To log users out of other third party sites, I recommend redirecting them further to the OAuth / OpenID providers after they logged out of your site.

HTTPS
-----
If you wish everything to go through HTTPS, set ``SOCIALREGISTRATION_USE_HTTPS`` in your settings file to
``True``.

Other Information
-----------------
If you don't wish your users to be redirected to the setup view to create a username but rather have
a random username generated for them, set ``SOCIALREGISTRATION_GENERATE_USERNAME`` in your settings file to ``True``.

If you want good logs of what is going on, configure logging according to _django_logging_docs. If you want it to log into a bucket other than the default of ``socialregistration`` set SOCIALREGISTRATION_LOGGER_NAME in your settings file to the desired logger name.


.. _django: http://code.djangoproject.com/
.. _oauth2: https://github.com/simplegeo/python-oauth2
.. _python-openid: https://github.com/openid/python-openid
.. _python-sdk: https://github.com/facebook/python-sdk
.. _django_logging_docs: https://docs.djangoproject.com/en/1.3/topics/logging/
