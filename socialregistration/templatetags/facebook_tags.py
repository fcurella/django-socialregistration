from django import template
from django.conf import settings
from django.core.urlresolvers import NoReverseMatch
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from socialregistration.utils import _https
from socialregistration.models import FacebookProfile

register = template.Library()

@register.inclusion_tag('socialregistration/facebook_js.html')
def facebook_js(requested_perms=""):
    return {'facebook_api_key' : getattr(settings, 'FACEBOOK_API_KEY', ''), 'is_https' : bool(_https()), 'requested_perms': requested_perms, 'MEDIA_URL': getattr(settings, 'MEDIA_URL', ''), 'STATIC_MEDIA_URL': getattr(settings, 'STATIC_MEDIA_URL', '')}


class FacebookButtonNode(template.Node):
    def render(self, context):
        if not 'request' in context:
            raise AttributeError, 'Please add the ``django.core.context_processors.request`` context processors to your settings.TEMPLATE_CONTEXT_PROCESSORS set'
        logged_in = context['request'].user.is_authenticated()
        if 'next' in context:
            next = context['next']
        else:
            next = None

        if 'socialregistration_connect_object' in context:
            # need to use this info to pass a GET parameter to the redirect so the object can be used when the user comes back
            obj = context['socialregistration_connect_object']
            cobj = {'app_label': obj._meta.app_label, 'model': obj._meta.module_name, 'key': obj.pk}
        else:
            cobj = {}

        context.update(
            dict(
                next=next,
                logged_in=logged_in,
                MEDIA_URL=getattr(settings, 'MEDIA_URL', ''),
                STATIC_MEDIA_URL=getattr(settings, 'STATIC_MEDIA_URL', ''),
                content_object=cobj
            )
        )
        try:
            rendered = render_to_string('socialregistration/facebook_button.html', context)
        except NoReverseMatch:
            rendered = ''
        context.pop()
        return mark_safe(rendered)

@register.tag
def facebook_button(parser, token):
    return FacebookButtonNode()

class FacebookInfoNode(template.Node):
    def __init__(self, var_name):
        self.var_name = var_name

    def render(self, context):
        # if the object is required, look for a Facebook account for it.
        if 'socialregistration_connect_object' in context:
            cobj = context['socialregistration_connect_object']
        # if not, check for the current user and make sure they're logged in and not anonymous
        else:
            cobj = context['request'].user
            if not cobj.is_authenticated():
                context[self.var_name] = None
                return ''

        try:
            profile = FacebookProfile.objects.for_object(cobj)
            context[self.var_name] = profile
            return ''
        except FacebookProfile.DoesNotExist:
            context[self.var_name] = None
            return ''

@register.tag
def facebook_info(parser, token):
    """
    Usage: {% facebook_info as fb %} Returns their Facebook Profile.
    """
    try:
        tag_info = token.split_contents()
        if len(tag_info) == 3:
            var_name = tag_info[2]
            return FacebookInfoNode(var_name)
        else:
            raise template.TemplateSyntaxError, "%r tag takes arguments." % token.contents.split()[0]
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag takes arguments." % token.contents.split()[0]


class FacebookConfiguredNode(template.Node):
    def __init__(self, var):
        self.var = var

    def render(self, context):
        context[self.var] = bool(getattr(settings, 'FACEBOOK_API_KEY', None))
        return ''

@register.tag
def facebook_configured(parser, token):
    bits = token.split_contents()
    if len(bits) != 3:
        raise template.TemplateSyntaxError('%s takes one arg' % bits[0])
    return FacebookConfiguredNode(bits[2])
