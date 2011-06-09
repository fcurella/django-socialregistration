from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site

from socialregistration.models import (FacebookProfile, TwitterProfile, OpenIDProfile)

class Auth(object):
    supports_object_permissions = False
    supports_anonymous_user = False
    supports_inactive_user = False
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

class FacebookAuth(Auth):
    def authenticate(self, uid=None):
        try:
            return FacebookProfile.objects.get(
                uid=uid,
                site=Site.objects.get_current(),
                content_type=ContentType.objects.get_for_model(User),
            ).content_object
        except FacebookProfile.DoesNotExist:
            return None

class TwitterAuth(Auth):
    def authenticate(self, twitter_id=None):
        try:
            return TwitterProfile.objects.get(
                twitter_id=twitter_id,
                site=Site.objects.get_current(),
                content_type=ContentType.objects.get_for_model(User),
            ).content_object
        except TwitterProfile.DoesNotExist:
            return None

class OpenIDAuth(Auth):
    def authenticate(self, identity=None):
        try:
            return OpenIDProfile.objects.get(
                identity=identity,
                site=Site.objects.get_current(),
                content_type=ContentType.objects.get_for_model(User),
            ).content_object
        except OpenIDProfile.DoesNotExist:
            return None
