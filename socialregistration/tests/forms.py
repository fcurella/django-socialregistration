from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from socialregistration.forms import UserForm, ExistingUser
from socialregistration.models import OpenIDProfile

class UserFormTest(TestCase):
    def test_unique_user(self):
        """
        Verifies unique case-insensitive usernames.
        """
        user = User()
        ct = ContentType.objects.get_for_model(User)
        profile = OpenIDProfile.objects.create(
            object_id=1,
            content_type=ct,
            identity='')

        form = UserForm(user, profile, {'username': 'bob', 'email': 'bob@bob.com'})
        self.assertTrue(form.is_valid())

        # now create an existing Bob
        User.objects.create(username='Bob', email='bob@bob.com')
        form = UserForm(user, profile, {'username': 'bob', 'email': 'bob@bob.com'})
        self.assertRaises(ExistingUser, form.is_valid)
