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

    def authenticate(self, **kwargs):
        remote_id = kwargs.get(self.model.remote_id_field)
        if not remote_id or len(kwargs) != 1:
            return None
        try:
            return self.model.objects.by_remote_id(remote_id).filter(
                content_type=ContentType.objects.get_for_model(User),
            ).get().content_object
        except self.model.DoesNotExist:
            return None

class FacebookAuth(Auth):
    model = FacebookProfile

class TwitterAuth(Auth):
    model = TwitterProfile

class OpenIDAuth(Auth):
    model = OpenIDProfile
