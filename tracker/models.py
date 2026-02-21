from django.db import models
from django.contrib.auth.models import User


class Meal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    calories = models.IntegerField()

    def __str__(self):
        return f"{self.name} ({self.user.username})"
