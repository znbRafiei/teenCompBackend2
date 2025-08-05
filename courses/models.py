from django.db import models
from accounts.models import User
# from .models import  DiscountCode
# Create your models here.
class Course(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    instructor = models.CharField(max_length=100)
    prerequisites = models.TextField(blank=True, null=True)
    duration_minutes = models.IntegerField()
    price = models.DecimalField(max_digits=6, decimal_places=2)
    course_image = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
class ShoppingCart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_token = models.CharField(max_length=100, null=True, blank=True)  # برای کاربران مهم نشده
    course = models.ForeignKey('Course', on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course', 'session_token')  # فقط یکی از user یا session_token باید پر باشه

    def __str__(self):
        return f"{self.user or self.session_token} - {self.course.title}"

class DiscountCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)  # مثل 10.00%
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code
    
class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_code = models.ForeignKey(DiscountCode, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('paid', 'Paid'),
            ('failed', 'Failed')
        ],
        default='pending'
    )

    def __str__(self):
        return f"Order {self.id} by {self.user.email}"
    
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.course.title} in Order {self.order.id}"

class Section(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    section_name = models.CharField(max_length=100)
    order_number = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.section_name} - {self.course.title}"
    
class Content(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('guide_card', 'Guide Card'),
        ('challenge', 'Challenge'),
    ]

    section = models.ForeignKey('Section', on_delete=models.CASCADE, related_name='contents')
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    title = models.CharField(max_length=100, blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)
    guide_text = models.TextField(blank=True, null=True)

    # فیلد اصلی برای چالش‌ها
    challenge_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title or self.content_type} ({self.content_type})"

    @property
    def course(self):
        return self.section.course
    
class UserProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    current_section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True)
    last_visited_content = models.ForeignKey(Content, on_delete=models.SET_NULL, null=True, blank=True)
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} - {self.course.title}"


class UserContentProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    watched_duration = models.FloatField(default=0.0)
    total_duration = models.FloatField(default=0.0)
    is_completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'content')

    def __str__(self):
        return f"{self.user.username} - {self.content.title}"
    
class ChallengeAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    attempt_number = models.IntegerField()  # 1, 2, 3
    is_successful = models.BooleanField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content', 'attempt_number')
    