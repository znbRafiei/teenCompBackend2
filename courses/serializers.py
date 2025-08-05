from rest_framework import serializers
from .models import (
    Course,
    ShoppingCart,
    DiscountCode,
    Order,
    Section,
    Content,
    UserProgress,
    OrderItem,
    UserContentProgress,
    ChallengeAttempt,
)
from accounts.models import User
from django.utils import timezone
from .utils import unlock_next_sections,can_access_challenge


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "description",
            "instructor",
            "prerequisites",
            "duration_minutes",
            "price",
            "created_at",
            "course_image",
        ]

    read_only_fields = ["id", "created_at"]

    # def validate_title(self, value):
    #     if Course.objects.filter(title=value).exists():
    #         raise serializers.ValidationError("A course with this title already exists.")
    #     return value
    def validate_title(self, value):
        course_id = self.instance.id if self.instance else None
        if Course.objects.filter(title=value).exclude(id=course_id).exists():
            raise serializers.ValidationError(
                "A course with this title already exists."
            )
        return value


# فقط برای ورودی
class AddToCartSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()

    def validate_course_id(self, value):
        if not Course.objects.filter(id=value).exists():
            raise serializers.ValidationError("Course does not exist.")
        return value


# برای خروجی
class CartItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="course.title")
    price = serializers.DecimalField(
        source="course.price", max_digits=6, decimal_places=2
    )

    class Meta:
        model = ShoppingCart
        fields = ["course_id", "title", "price"]


class DiscountCodeSerializer(serializers.Serializer):
    code = serializers.CharField()

    def validate_code(self, value):
        try:
            discount = DiscountCode.objects.get(code=value)
        except DiscountCode.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired discount code.")

        if not discount.is_active:
            raise serializers.ValidationError("This discount code is not active.")

        if discount.valid_to < timezone.now():
            raise serializers.ValidationError("This discount code has expired.")

        return discount


class CheckoutSerializer(serializers.Serializer):
    discount_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        request = self.context.get("request")
        cart_items = []

        if request.user.is_authenticated:
            cart_items = ShoppingCart.objects.filter(user=request.user)
        else:
            session_token = request.session.session_key
            if not session_token:
                raise serializers.ValidationError("No active cart found.")
            cart_items = ShoppingCart.objects.filter(session_token=session_token)

        if not cart_items.exists():
            raise serializers.ValidationError("Your cart is empty.")

        # چک کردن کد تخفیف
        discount_code = data.get("discount_code")
        if discount_code:
            try:
                discount = DiscountCode.objects.get(code=discount_code)
                if not discount.is_active:
                    raise serializers.ValidationError(
                        "This discount code is not active."
                    )
                if discount.valid_to < timezone.now():
                    raise serializers.ValidationError("This discount code has expired.")
                data["discount_code"] = discount
            except DiscountCode.DoesNotExist:
                raise serializers.ValidationError("Invalid or expired discount code.")

        data["cart_items"] = cart_items
        return data


class PurchasedCourseSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    purchased_at = serializers.DateTimeField()


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "section_name", "order_number", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        # در View چک می‌شه، ولی برای امنیت بیشتر اینجا هم می‌تونیم چک کنیم
        return data


class VideoContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "video_url", "content_type", "created_at"]
        read_only_fields = ["id", "content_type", "created_at"]

    def validate(self, data):
        if not data.get("title"):
            raise serializers.ValidationError({"title": "This field is required."})
        if not data.get("video_url"):
            raise serializers.ValidationError({"video_url": "This field is required."})
        return data


class GuideCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "guide_text", "content_type", "created_at"]
        read_only_fields = ["id", "content_type", "created_at"]

    def validate(self, data):
        if not data.get("title"):
            raise serializers.ValidationError({"title": "This field is required."})
        if not data.get("guide_text"):
            raise serializers.ValidationError({"guide_text": "This field is required."})
        return data


class ChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "challenge_data", "content_type", "created_at"]
        read_only_fields = ["id", "content_type", "created_at"]

    def validate_challenge_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Challenge data must be a valid JSON object."
            )
        if "type" not in value:
            raise serializers.ValidationError("Challenge type is required.")
        return value

    def validate(self, data):
        challenge_data = data.get("challenge_data")
        if not challenge_data:
            raise serializers.ValidationError(
                {"challenge_data": "This field is required."}
            )

        challenge_type = challenge_data.get("type")
        required_fields = {
            "multiple_choice_single": ["question", "options", "correct_option"],
            "multiple_choice_multiple": ["question", "options", "correct_options"],
            "drag_drop_table": ["question", "columns"],  # بدون correct_pairs
            "image_based_mcq": ["question", "image_urls", "sub_questions"],
            "descriptive": ["question", "sub_questions"],
        }

        if challenge_type not in required_fields:
            raise serializers.ValidationError({"type": "Invalid challenge type."})

        for field in required_fields[challenge_type]:
            if field not in challenge_data:
                raise serializers.ValidationError(
                    {field: f"This field is required for {challenge_type}."}
                )

        return data


class AdminCourseListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["title", "instructor", "course_image"]


class CourseOutlineSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["title", "sections"]

    def get_sections(self, obj):
        return [
            section.section_name
            for section in obj.sections.all().order_by("order_number")
        ]


class MyCourseSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "description",
            "instructor",
            "duration_minutes",
            "price",
            "course_image",
            "progress",
        ]

    def get_progress(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            progress = UserProgress.objects.get(user=request.user, course=obj)
            return {
                "completed": progress.completed,
                "last_section": (
                    progress.last_section.section_name
                    if progress.last_section
                    else None
                ),
                "last_content": (
                    progress.last_content.title if progress.last_content else None
                ),
                "updated_at": progress.updated_at,
            }
        except UserProgress.DoesNotExist:
            return {
                "completed": False,
                "last_section": None,
                "last_content": None,
                "updated_at": None,
            }


class PurchaseHistorySerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title")
    course_price = serializers.DecimalField(
        source="course.price", max_digits=10, decimal_places=2
    )

    class Meta:
        model = OrderItem
        fields = ["course_title", "course_price"]

class HomePageCourseSerializer(serializers.ModelSerializer):
    buyer_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            'id',
            'title',
            'course_image',
            'instructor',
            'description',
            'price',
            'buyer_count'
        ]
        
class CourseSectionStatusSerializer(serializers.ModelSerializer):
    is_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ['id', 'section_name', 'order_number', 'is_unlocked']

    def get_is_unlocked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False

        user = request.user
        course = obj.course

        # سرفصل اول همیشه بازه
        if obj.order_number == 1:
            return True

        # چک کردن تمام سرفصل‌هایی که ویدیویشون ۸۰٪ دیده شده
        for section in Section.objects.filter(course=course):
            try:
                video_content = section.contents.get(content_type='video')
                progress = video_content.usercontentprogress_set.get(user=user)
                if progress.is_completed:
                    # اگر ویدیو ۸۰٪ دیده شده، دو سرفصل بعدی باز میشن
                    next_sections = unlock_next_sections(user, section)
                    if obj in next_sections:
                        return True
            except:
                continue

        # چک کردن اینکه آیا کاربر در حال حاضر در guide card است و مجاز به ورود به challenge است
        try:
            current_guide_content = obj.contents.get(content_type='guide_card')
            if can_access_challenge(user, current_guide_content):
                return True
        except:
            pass

        return False
    
class VideoProgressSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()
    is_completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserContentProgress
        fields = ['watched_duration', 'total_duration', 'progress_percent', 'is_completed', 'updated_at']

    def get_progress_percent(self, obj):
        if obj.total_duration > 0:
            return round((obj.watched_duration / obj.total_duration) * 100, 2)
        return 0
    
class ContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = [
            'id', 'title', 'content_type',
            'video_url', 'guide_text', 'challenge_data'
        ]


class ChallengeAttemptSummarySerializer(serializers.Serializer):
    attempt_count = serializers.IntegerField()
    max_attempts = serializers.IntegerField(default=3)
    is_successful = serializers.BooleanField(allow_null=True)
    can_retry = serializers.BooleanField(default=True)


class SectionContentSerializer(serializers.Serializer):
    access_granted = serializers.BooleanField()
    message = serializers.CharField()
    content = ContentSerializer(many=True, read_only=True)
    challenge_attempts = ChallengeAttemptSummarySerializer(required=False)
    
class SubmitChallengeSerializer(serializers.Serializer):
    answers = serializers.ListField(child=serializers.CharField(), required=True)

class ChallengeAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChallengeAttempt
        fields = ['attempt_number', 'is_successful', 'submitted_at']