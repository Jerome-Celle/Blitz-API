import json

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from django.urls import reverse
from django.contrib.auth import get_user_model

from ..factories import UserFactory
from ..models import ActionToken, TemporaryToken

User = get_user_model()


class UsersActivationTests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.user = UserFactory()
        self.user.set_password('Test123!')
        self.user.is_active = False
        self.user.save()

        self.activation_token = ActionToken.objects.create(
            user=self.user,
            type='account_activation',
        )
        self.email_change_token = ActionToken.objects.create(
            user=self.user,
            type='email_change',
            data={
                'email': "new_email@mailinator.com",
            }
        )

    def test_activate_user(self):
        """
        Ensure we can activate a user by using an ActionToken.
        """
        data = {
            'activation_token': self.activation_token.key,
        }

        response = self.client.post(
            reverse('users_activation'),
            data,
            format='json',
        )

        response_data = json.loads(response.content)

        # It's the good user
        self.assertEqual(response_data['user']['id'], self.user.id)

        # We read a new time the user to be synchronized
        user_sync = User.objects.get(id=self.user.id)

        # The user is now active
        self.assertTrue(user_sync.is_active)

        # A temporary authentication token has been created and returned
        auth_token = TemporaryToken.objects.filter(
            user=user_sync,
        )
        self.assertTrue(auth_token.count() == 1)
        self.assertEqual(response_data['token'], auth_token[0].key)

        # The activation token has been removed
        tokens = ActionToken.objects.filter(
            user=user_sync,
            type='account_activation',
        )
        self.assertTrue(len(tokens) == 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_email_change(self):
        """
        Ensure we can activate a new email using an "email_change" ActionToken.
        """
        data = {
            'activation_token': self.email_change_token.key,
        }

        response = self.client.post(
            reverse('users_activation'),
            data,
            format='json',
        )

        response_data = json.loads(response.content)

        # It's the good user
        self.assertEqual(response_data['user']['id'], self.user.id)

        # We read a new time the user to be synchronized
        user_sync = User.objects.get(id=self.user.id)

        # The user's email is updated
        self.assertEqual(
            user_sync.email,
            self.email_change_token.data['email'],
        )

        # A temporary authentication token has been created and returned
        auth_token = TemporaryToken.objects.filter(
            user=user_sync,
        )
        self.assertTrue(auth_token.count() == 1)
        self.assertEqual(response_data['token'], auth_token[0].key)

        # The activation token has been removed
        tokens = ActionToken.objects.filter(
            user=user_sync,
            type='email_change',
        )
        self.assertTrue(len(tokens) == 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_activate_user_with_bad_token(self):
        """
        Ensure we can't activate a user without a good ActionToken.
        """
        self.client.force_authenticate(user=self.user)

        data = {
            'activation_token': 'bad_token',
        }

        response = self.client.post(
            reverse('users_activation'),
            data,
            format='json',
        )

        content = {'detail': '"bad_token" is not a valid activation_token.'}
        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
