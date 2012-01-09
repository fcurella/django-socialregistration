from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.db import models

class SocialProfileManager(models.Manager):
    def for_user_by_username(self, username):
        user = User.objects.get(username=username)
        return self.for_user_by_id(user.pk)

    def on_current_site(self):
        return self.filter(site=Site.objects.get_current())

    def for_user_by_id(self, user_id):
        return self.on_current_site().get(
            content_type=ContentType.objects.get_for_model(User),
            object_id=user_id)

    def for_object_content_type(self, obj):
        return self.on_current_site().filter(
            content_type=ContentType.objects.get_for_model(obj.__class__))

    def for_object(self, obj):
        return self.for_object_content_type(obj).get(object_id=obj.pk)

    def by_remote_id(self, identity):
        return self.on_current_site().filter(**{self.model.remote_id_field: identity})
