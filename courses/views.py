from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
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
from .serializers import (
    CourseSerializer,
    AddToCartSerializer,
    CartItemSerializer,
    DiscountCodeSerializer,
    CheckoutSerializer,
    PurchasedCourseSerializer,
    SectionSerializer,
    VideoContentSerializer,
    GuideCardSerializer,
    ChallengeSerializer,
    AdminCourseListSerializer,
    CourseOutlineSerializer,
    MyCourseSerializer,
    PurchaseHistorySerializer,
    HomePageCourseSerializer,
    CourseSectionStatusSerializer,
    VideoProgressSerializer,
    ContentSerializer,
    ChallengeAttemptSummarySerializer,
    SectionContentSerializer,
    SubmitChallengeSerializer,
)
from django.utils import timezone
from accounts.models import User
from django.db.models import Count, Q 
from .utils import can_access_challenge
from .ai_evaluator import evaluate_answer_with_ai

class ListCoursesView(APIView):
    def get(self, request):
        courses = Course.objects.all()
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CourseDetailsView(APIView):
    def get(self, request, course_id):
        try:
            course = Course.objects.get(id=course_id)
            serializer = CourseSerializer(course)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )


class AddToCartView(APIView):
    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        course_id = serializer.validated_data["course_id"]

        # بررسی وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course does not exist."}, status=status.HTTP_400_BAD_REQUEST
            )

        # کاربر لاگین شده؟
        if request.user.is_authenticated:
            cart_item, created = ShoppingCart.objects.get_or_create(
                user=request.user, course_id=course_id, defaults={"session_token": None}
            )
            if not created:
                return Response(
                    {"error": "Course is already in the cart."},
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            # استفاده از session token
            session_token = request.session.session_key
            if not session_token:
                request.session.save()
                session_token = request.session.session_key

            cart_item, created = ShoppingCart.objects.get_or_create(
                session_token=session_token,
                course_id=course_id,
                defaults={"user": None},
            )

            if not created:
                return Response(
                    {"error": "Course is already in the cart."},
                    status=status.HTTP_409_CONFLICT,
                )

        # لیست سبد خرید کاربر
        cart_items = ShoppingCart.objects.filter(
            user=request.user if request.user.is_authenticated else None,
            session_token=session_token if not request.user.is_authenticated else None,
        )
        cart_serializer = CartItemSerializer(cart_items, many=True)

        return Response({"cart_items": cart_serializer.data}, status=status.HTTP_200_OK)


class ViewCartView(APIView):
    def get(self, request):
        cart_items = []

        # کاربر لاگین شده
        if request.user.is_authenticated:
            cart_items = ShoppingCart.objects.filter(user=request.user)

        # کاربر مهم نیست، از session استفاده می‌کنیم
        else:
            session_token = request.session.session_key
            if not session_token:
                request.session.save()
                session_token = request.session.session_key

            cart_items = ShoppingCart.objects.filter(session_token=session_token)

        # سریالایز کردن داده‌ها
        serializer = CartItemSerializer(cart_items, many=True)

        # محاسبه قیمت کل
        total_price = sum(item.course.price for item in cart_items)

        return Response(
            {"cart_items": serializer.data, "total_price": total_price},
            status=status.HTTP_200_OK,
        )


class RemoveFromCartView(APIView):
    def delete(self, request, course_id):
        # بررسی وضعیت کاربر
        if request.user.is_authenticated:
            try:
                cart_item = ShoppingCart.objects.get(
                    user=request.user, course_id=course_id
                )
                cart_item.delete()
            except ShoppingCart.DoesNotExist:
                return Response(
                    {"error": "Course not found in the cart."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            session_token = request.session.session_key
            if not session_token:
                return Response(
                    {"error": "No active cart found for this session."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                cart_item = ShoppingCart.objects.get(
                    session_token=session_token, course_id=course_id
                )
                cart_item.delete()
            except ShoppingCart.DoesNotExist:
                return Response(
                    {"error": "Course not found in the cart."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # بازگرداندن سبد خرید جدید
        cart_items = ShoppingCart.objects.filter(
            user=request.user if request.user.is_authenticated else None,
            session_token=session_token if not request.user.is_authenticated else None,
        )
        serializer = CartItemSerializer(cart_items, many=True)
        total_price = sum(item.course.price for item in cart_items)

        return Response(
            {"cart_items": serializer.data, "total_price": total_price},
            status=status.HTTP_200_OK,
        )


class ApplyDiscountCodeView(APIView):
    def post(self, request):
        serializer = DiscountCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        discount = serializer.validated_data

        # دریافت سبد خرید
        if request.user.is_authenticated:
            cart_items = ShoppingCart.objects.filter(user=request.user)
        else:
            session_token = request.session.session_key
            if not session_token:
                return Response(
                    {"error": "No active cart found."}, status=status.HTTP_404_NOT_FOUND
                )
            cart_items = ShoppingCart.objects.filter(session_token=session_token)

        if not cart_items.exists():
            return Response(
                {"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        total_price_before_discount = sum(item.course.price for item in cart_items)
        total_price_after_discount = total_price_before_discount * (
            1 - discount.discount_percent / 100
        )

        return Response(
            {
                "cart_items": CartItemSerializer(cart_items, many=True).data,
                "discount_code": discount.code,
                "total_price_before_discount": total_price_before_discount,
                "total_price_after_discount": total_price_after_discount,
            },
            status=status.HTTP_200_OK,
        )


class CheckoutView(APIView):
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cart_items = serializer.validated_data["cart_items"]
        discount_code = serializer.validated_data.get("discount_code", None)

        total_price = sum(item.course.price for item in cart_items)
        if discount_code:
            total_price = total_price * (1 - discount_code.discount_percent / 100)

        # ایجاد سفارش
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            total_amount=total_price,
            discount_code=discount_code,
        )

        # پاک کردن سبد خرید بعد از خرید
        if request.user.is_authenticated:
            ShoppingCart.objects.filter(user=request.user).delete()
        else:
            session_token = request.session.session_key
            if session_token:
                ShoppingCart.objects.filter(session_token=session_token).delete()

        # هدایت به درگاه پرداخت (در اینجا فقط یه URL می‌سازیم)
        payment_url = f"https://payment.gateway.example.com/transaction/ {order.id}"

        return Response(
            {
                "order_id": order.id,
                "total_amount": total_price,
                "payment_url": payment_url,
            },
            status=status.HTTP_200_OK,
        )


# class SimulatePaymentView(APIView):
#     def post(self, request):
#         if not request.user.is_authenticated:
#             return Response(
#                 {"error": "Authentication required."},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )

#         # گرفتن آیتم‌های سبد خرید کاربر
#         cart_items = ShoppingCart.objects.filter(user=request.user)
#         if not cart_items.exists():
#             return Response(
#                 {"error": "Your cart is empty."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # فعال‌سازی دسترسی به همه دوره‌های سبد خرید
#         for item in cart_items:
#             UserProgress.objects.get_or_create(
#                 user=request.user,
#                 course=item.course,
#                 defaults={'completed': False}
#             )

#         # پاک کردن سبد خرید
#         cart_items.delete()

#         # جمع‌آوری اطلاعات دوره‌های خریداری‌شده
#         purchased_courses = [
#             {
#                 "course_id": item.course.id,
#                 "title": item.course.title,
#                 "price": float(item.course.price)
#             }
#             for item in cart_items
#         ]

#         return Response({
#             "message": "Payment simulated successfully. Access granted to all courses.",
#             "purchased_courses": [  # دوباره ساخته میشه چون cart_items حذف شد
#                 {
#                     "course_id": item.course.id,
#                     "title": item.course.title,
#                     "price": float(item.course.price)
#                 }
#                 for item in ShoppingCart.objects.filter(user=request.user).prefetch_related('course')
#             ]
#         }, status=status.HTTP_200_OK)


class SimulatePaymentView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        cart_items = ShoppingCart.objects.filter(user=request.user).select_related(
            "course"
        )
        if not cart_items.exists():
            return Response(
                {"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        # محاسبه قیمت کل
        total_price = sum(float(item.course.price) for item in cart_items)

        # ایجاد سفارش با status='paid'
        order = Order.objects.create(
            user=request.user, total_amount=total_price, status="paid"
        )

        # ایجاد OrderItem برای هر دوره
        for item in cart_items:
            OrderItem.objects.create(order=order, course=item.course)
            # ایجاد دسترسی
            UserProgress.objects.get_or_create(
                user=request.user, course=item.course, defaults={"completed": False}
            )

        # پاک کردن سبد خرید
        cart_items.delete()

        return Response(
            {
                "message": "Payment simulated successfully. Access granted and purchase history updated.",
                "order_id": order.id,
                "total_amount": total_price,
            },
            status=status.HTTP_200_OK,
        )


class CreateCourseView(APIView):
    def post(self, request):
        # چک کردن احراز هویت
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # چک کردن نام کاربری ادمین
        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to create courses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # سریالایز کردن و اعتبارسنجی داده‌ها
        serializer = CourseSerializer(data=request.data)
        if serializer.is_valid():
            course = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateCourseView(APIView):
    def put(self, request, course_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to update courses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = CourseSerializer(course, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteCourseView(APIView):
    def delete(self, request, course_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        course.delete()
        return Response(
            {"message": "Course deleted successfully."}, status=status.HTTP_200_OK
        )


class UserPurchasedCoursesView(APIView):
    def get(self, request, user_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # گرفتن تمام سفارش‌های paid شده
        orders = Order.objects.filter(user=user, status="paid").select_related("course")
        if not orders.exists():
            return Response([], status=status.HTTP_200_OK)

        # گرفتن اطلاعات دوره‌های خریداری‌شده
        purchased_courses = []
        for order in orders:
            purchased_courses.append(
                {
                    "course_id": order.course.id,
                    "title": order.course.title,
                    "price": float(order.total_amount),
                    "purchased_at": order.created_at,
                }
            )

        return Response(purchased_courses, status=status.HTTP_200_OK)


class CreateSectionView(APIView):
    def post(self, request, course_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to create sections."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        data = request.data.copy()
        serializer = SectionSerializer(data=data)
        if serializer.is_valid():
            section = serializer.save(course=course)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateSectionView(APIView):
    def put(self, request, course_id, section_id):
        # ۱. احراز هویت ادمین
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ۲. چک کردن وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # ۳. چک کردن وجود سرفصل و تعلق آن به دوره
        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            return Response(
                {"error": "Section not found or does not belong to this course."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۴. آپدیت سرفصل
        serializer = SectionSerializer(section, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteSectionView(APIView):
    def delete(self, request, course_id, section_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            return Response(
                {"error": "Section not found or does not belong to this course."},
                status=status.HTTP_404_NOT_FOUND,
            )

        section.delete()
        return Response(
            {"message": "Section deleted successfully."}, status=status.HTTP_200_OK
        )


class CreateContentView(APIView):
    def post(self, request, course_id, section_id):
        # ۱. احراز هویت ادمین
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ۲. چک کردن وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # ۳. چک کردن وجود سرفصل و تعلق آن به دوره
        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            return Response(
                {"error": "Section not found or does not belong to this course."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۴. چک کردن وجود محتوا در این سرفصل (محدودیت منطقی)
        if Content.objects.filter(section=section).exists():
            return Response(
                {
                    "error": "This section already has a content. Only one content is allowed per section."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ۵. تعیین نوع محتوا
        content_type = request.data.get("content_type")

        if content_type == "video":
            serializer = VideoContentSerializer(data=request.data)
            if serializer.is_valid():
                # ایجاد محتوا با content_type مشخص
                content = Content.objects.create(
                    section=section,
                    content_type="video",
                    title=serializer.validated_data["title"],
                    video_url=serializer.validated_data["video_url"],
                )
                return Response(
                    VideoContentSerializer(content).data, status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif content_type == "guide_card":
            serializer = GuideCardSerializer(data=request.data)
            if serializer.is_valid():
                content = Content.objects.create(
                    section=section,
                    content_type="guide_card",
                    title=serializer.validated_data["title"],
                    guide_text=serializer.validated_data["guide_text"],
                )
                return Response(
                    GuideCardSerializer(content).data, status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif content_type == "challenge":
            serializer = ChallengeSerializer(data=request.data)
            if serializer.is_valid():
                content = Content.objects.create(
                    section=section,
                    content_type="challenge",
                    title=request.data.get("title"),
                    challenge_data=request.data.get("challenge_data"),
                )
                return Response(
                    ChallengeSerializer(content).data, status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response(
                {
                    "error": "Invalid content type. Must be 'video', 'guide_card', or 'challenge'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class UpdateContentBySectionView(APIView):
    def put(self, request, course_id, section_id):
        # ۱. احراز هویت ادمین
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ۲. چک کردن وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # ۳. چک کردن وجود سرفصل و تعلق آن به دوره
        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            return Response(
                {"error": "Section not found or does not belong to this course."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۴. چک کردن وجود محتوا در این سرفصل
        try:
            content = Content.objects.get(section=section)
        except Content.DoesNotExist:
            return Response(
                {"error": "No content found for this section."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۵. انتخاب Serializer بر اساس نوع محتوا
        if content.content_type == "video":
            serializer = VideoContentSerializer(
                content, data=request.data, partial=True
            )
        elif content.content_type == "guide_card":
            serializer = GuideCardSerializer(content, data=request.data, partial=True)
        elif content.content_type == "challenge":
            serializer = ChallengeSerializer(content, data=request.data, partial=True)
        else:
            return Response(
                {"error": "Invalid content type."}, status=status.HTTP_400_BAD_REQUEST
            )

        # ۶. اعتبارسنجی و آپدیت
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteContentBySectionView(APIView):
    def delete(self, request, course_id, section_id):
        # ۱. احراز هویت ادمین
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ۲. چک کردن وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # ۳. چک کردن وجود سرفصل و تعلق آن به دوره
        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            return Response(
                {"error": "Section not found or does not belong to this course."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۴. چک کردن وجود محتوا در این سرفصل
        try:
            content = Content.objects.get(section=section)
        except Content.DoesNotExist:
            return Response(
                {"error": "No content found for this section."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ۵. حذف محتوا
        content.delete()
        return Response(
            {"message": "Content deleted successfully."}, status=status.HTTP_200_OK
        )


class ListAllCoursesAdminView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        courses = Course.objects.all()
        serializer = AdminCourseListSerializer(courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CourseOutlineView(APIView):
    def get(self, request, course_id):
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = CourseOutlineSerializer(course)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyCoursesView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # گرفتن تمام دوره‌هایی که کاربر بهشون دسترسی داره
        user_courses = Course.objects.filter(userprogress__user=request.user).distinct()

        serializer = MyCourseSerializer(
            user_courses, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PurchaseHistoryView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # ✅ گرفتن OrderItems از طریق Orderهای paid
        order_items = OrderItem.objects.filter(
            order__user=request.user,
            order__status='paid'
        ).select_related('course')

        serializer = PurchaseHistorySerializer(order_items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class HomePageCoursesView(APIView):
    def get(self, request):
        # گرفتن تمام دوره‌ها + محاسبه تعداد خریداران (خریدهای موفق)
        courses = Course.objects.annotate(
            buyer_count=Count(
                'orderitem__order',
                filter=Q(orderitem__order__status='paid')
            )
        ).order_by('-created_at')  # جدیدترین اول

        serializer = HomePageCourseSerializer(courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class TopSellingCoursesView(APIView):
    def get(self, request):
        # گرفتن تمام دوره‌ها + مرتب‌سازی بر اساس تعداد خریداران (بیشترین اول)
        courses = Course.objects.annotate(
            buyer_count=Count(
                'orderitem__order',
                filter=Q(orderitem__order__status='paid')
            )
        ).order_by('-buyer_count', 'created_at')  # اول بر اساس فروش، بعد بر اساس تاریخ

        serializer = HomePageCourseSerializer(courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class CourseSectionsStatusView(APIView):
    def get(self, request, course_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        sections = Section.objects.filter(course=course).order_by('order_number')
        serializer = CourseSectionStatusSerializer(
            sections,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class SubmitVideoProgressView(APIView):
    def post(self, request, content_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            content = Content.objects.get(id=content_id, content_type='video')
        except Content.DoesNotExist:
            return Response(
                {"error": "Video content not found or is not a video."},
                status=status.HTTP_404_NOT_FOUND
            )

        watched_seconds = request.data.get("watched_seconds")
        total_seconds = request.data.get("total_seconds")

        if watched_seconds is None or total_seconds is None:
            return Response(
                {"error": "watched_seconds and total_seconds are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            watched_seconds = float(watched_seconds)
            total_seconds = float(total_seconds)
        except (ValueError, TypeError):
            return Response(
                {"error": "watched_seconds and total_seconds must be numbers."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if watched_seconds < 0 or total_seconds <= 0 or watched_seconds > total_seconds:
            return Response(
                {"error": "Invalid time values."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # گرفتن یا ایجاد پیشرفت کاربر
        progress, created = UserContentProgress.objects.get_or_create(
            user=request.user,
            content=content,
            defaults={
                'total_duration': total_seconds
            }
        )

        # بروزرسانی پیشرفت
        progress.watched_duration = watched_seconds
        progress.total_duration = total_seconds

        # محاسبه تکمیل بودن (80%)
        progress.is_completed = (watched_seconds / total_seconds) >= 0.8

        progress.save()

        # سریالایزر برای خروجی
        serializer = VideoProgressSerializer(progress)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
# class CheckNextSectionAccessView(APIView):
#     def post(self, request):
#         if not request.user.is_authenticated:
#             return Response(
#                 {"error": "Authentication required."},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )

#         current_section_id = request.data.get("current_section_id")
#         if not current_section_id:
#             return Response(
#                 {"error": "current_section_id is required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             current_section = Section.objects.get(id=current_section_id)
#         except Section.DoesNotExist:
#             return Response(
#                 {"error": "Current section not found."},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         # پیدا کردن سرفصل بعدی
#         try:
#             next_section = Section.objects.get(
#                 course=current_section.course,
#                 order_number=current_section.order_number + 1
#             )
#         except Section.DoesNotExist:
#             return Response({
#                 "access_granted": False,
#                 "message": "This is the last section."
#             })

#         # چک کردن اینکه آیا کاربر ۸۰٪ ویدیوی سرفصل فعلی رو دیده
#         try:
#             video_content = current_section.contents.get(content_type='video')
#             progress = UserContentProgress.objects.get(
#                 user=request.user,
#                 content=video_content
#             )
#             if not progress.is_completed:
#                 return Response({
#                     "access_granted": False,
#                     "message": "You must watch 80% of the video to proceed."
#                 })
#         except:
#             return Response({
#                 "access_granted": False,
#                 "message": "Video not found or progress not tracked."
#             })

#         # اگر دیده بود، دسترسی داره
#         contents = Content.objects.filter(section=next_section)

#         # جمع‌آوری اطلاعات چالش (اگر وجود داشته باشه)
#         challenge_attempts_data = None
#         challenge_content = contents.filter(content_type='challenge').first()
#         if challenge_content:
#             attempts = ChallengeAttempt.objects.filter(
#                 user=request.user,
#                 content=challenge_content
#             ).order_by('-submitted_at')
#             attempt_count = attempts.count()
#             is_successful = attempts.filter(is_successful=True).exists()

#             challenge_attempts_data = {
#                 "attempt_count": attempt_count,
#                 "max_attempts": 3,
#                 "is_successful": is_successful
#             }

#         # سریالایزر خروجی
#         serializer = NextSectionAccessSerializer({
#             "access_granted": True,
#             "message": "Access granted to next section.",
#             "content": contents,
#             "challenge_attempts": challenge_attempts_data
#         })

#         return Response(serializer.data, status=status.HTTP_200_OK)
class CheckNextSectionAccessView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        current_section_id = request.data.get("current_section_id")
        if not current_section_id:
            return Response(
                {"error": "current_section_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            current_section = Section.objects.get(id=current_section_id)
        except Section.DoesNotExist:
            return Response(
                {"error": "Current section not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # پیدا کردن سرفصل بعدی
        try:
            next_section = Section.objects.get(
                course=current_section.course,
                order_number=current_section.order_number + 1
            )
        except Section.DoesNotExist:
            return Response({
                "access_granted": False,
                "message": "This is the last section."
            })

        # 1️⃣ چک کردن دسترسی از "فیلم" به "کارت راهنما"
        try:
            video_content = current_section.contents.get(content_type='video')
            progress = UserContentProgress.objects.get(
                user=request.user,
                content=video_content
            )
            if progress.is_completed:
                contents = Content.objects.filter(section=next_section)
                return Response({
                    "access_granted": True,
                    "message": "Access granted to next section (guide card).",
                    "content": ContentSerializer(contents, many=True).data,
                    "challenge_attempts": None
                }, status=status.HTTP_200_OK)
        except:
            pass  # اگر ویدیو نبود یا پیشرفت نداشت، ادامه بده

        # 2️⃣ چک کردن دسترسی از "کارت راهنما" به "چالش"
        try:
            guide_content = current_section.contents.get(content_type='guide_card')
            # اگر کاربر به این مرحله رسیده، فرض می‌کنیم کارت راهنما رو دیده
            contents = Content.objects.filter(section=next_section)

            # جمع‌آوری اطلاعات چالش (اگر وجود داشته باشه)
            challenge_attempts_data = None
            challenge_content = contents.filter(content_type='challenge').first()
            if challenge_content:
                attempts = ChallengeAttempt.objects.filter(
                    user=request.user,
                    content=challenge_content
                ).order_by('-submitted_at')
                attempt_count = attempts.count()
                is_successful = attempts.filter(is_successful=True).exists()

                challenge_attempts_data = {
                    "attempt_count": attempt_count,
                    "max_attempts": 3,
                    "is_successful": is_successful
                }

            return Response({
                "access_granted": True,
                "message": "Access granted to next section (challenge).",
                "content": ContentSerializer(contents, many=True).data,
                "challenge_attempts": challenge_attempts_data
            }, status=status.HTTP_200_OK)
        except:
            pass  # اگر کارت راهنما نبود، ادامه بده

        # ❌ اگر هیچ شرطی برقرار نشد
        return Response({
            "access_granted": False,
            "message": "You must complete the current section to proceed."
        }, status=status.HTTP_403_FORBIDDEN)
        
        
class GetCurrentSectionContent(APIView):
    def get(self, request, course_id, current_section_order):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # ۱. چک کردن وجود دوره
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ۲. چک کردن دسترسی کاربر به دوره
        if not UserProgress.objects.filter(user=request.user, course=course).exists():
            return Response(
                {"error": "You don't have access to this course."},
                status=status.HTTP_403_FORBIDDEN
            )

        # ۳. تبدیل current_section_order به عدد
        try:
            current_section_order = int(current_section_order)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid section order number."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ۴. گرفتن سرفصل با order_number مشخص
        try:
            section = Section.objects.get(
                course=course,
                order_number=current_section_order
            )
        except Section.DoesNotExist:
            return Response(
                {"error": "Section with this order number not found in the course."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ۵. گرفتن محتوای این سرفصل
        contents = Content.objects.filter(section=section).order_by('id')

        # ۶. سریالایز و ارسال
        serializer = ContentSerializer(contents, many=True)
        return Response({
            "section_order": current_section_order,
            "content_count": len(serializer.data),
            "content": serializer.data
        }, status=status.HTTP_200_OK)
        
# class SubmitChallengeView(APIView):
#     def post(self, request, challenge_id):
#         if not request.user.is_authenticated:
#             return Response(
#                 {"error": "Authentication required."},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )

#         try:
#             challenge_content = Content.objects.get(
#                 id=challenge_id,
#                 content_type='challenge'
#             )
#         except Content.DoesNotExist:
#             return Response(
#                 {"error": "Challenge not found."},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         section = challenge_content.section
#         course = section.course

#         # چک کردن اینکه آیا کاربر ۸۰٪ ویدیوی سرفصل قبلی رو دیده
#         try:
#             prev_section = Section.objects.get(
#                 course=course,
#                 order_number=section.order_number - 1
#             )
#             video_content = prev_section.contents.get(content_type='video')
#             progress = UserContentProgress.objects.get(
#                 user=request.user,
#                 content=video_content
#             )
#             if not progress.is_completed:
#                 return Response({
#                     "error": "You must watch 80% of the previous video to attempt this challenge."
#                 }, status=status.HTTP_403_FORBIDDEN)
#         except:
#             return Response({
#                 "error": "Prerequisite video not found or not completed."
#             }, status=status.HTTP_403_FORBIDDEN)

#         # دیسیریالایز و اعتبارسنجی پاسخ
#         serializer = SubmitChallengeSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(
#                 {"error": "Invalid input."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         user_answers = serializer.validated_data['answers']
#         correct_answer = challenge_content.challenge_data.get('correct_answer')

#         # بررسی پاسخ
#         is_correct = user_answers == [correct_answer]  # یا منطق پیچیده‌تر برای چندگزینه‌ای

#         # ثبت تلاش
#         attempt_number = ChallengeAttempt.objects.filter(
#             user=request.user,
#             content=challenge_content
#         ).count() + 1

#         ChallengeAttempt.objects.create(
#             user=request.user,
#             content=challenge_content,
#             attempt_number=attempt_number,
#             is_successful=is_correct
#         )

#         # 🔹 اگر پاسخ درست بود
#         if is_correct:
#             # باز کردن سرفصل بعدی
#             try:
#                 next_section = Section.objects.get(
#                     course=course,
#                     order_number=section.order_number + 1
#                 )
#                 # در اینجا می‌تونی یه تابع utility فراخوانی کنیم
#                 # ولی برای سادگی، فقط یه پیام می‌دیم
#                 return Response({
#                     "is_correct": True,
#                     "message": "Challenge passed! Next section unlocked.",
#                     "next_section_unlocked": True
#                 }, status=status.HTTP_200_OK)
#             except Section.DoesNotExist:
#                 return Response({
#                     "is_correct": True,
#                     "message": "Challenge passed! This is the last section.",
#                     "next_section_unlocked": False
#                 }, status=status.HTTP_200_OK)

#         # 🔹 اگر پاسخ غلط بود
#         if attempt_number >= 3:
#             # ❌ ۳ تلاش شکست خورده → قفل سرفصل فعلی و قبلی + ریست پیشرفت
#             try:
#                 # ریست پیشرفت ویدیوی سرفصل قبلی
#                 prev_video = prev_section.contents.get(content_type='video')
#                 UserContentProgress.objects.filter(
#                     user=request.user,
#                     content=prev_video
#                 ).update(
#                     watched_duration=0,
#                     total_duration=prev_video.total_duration or 0,
#                     is_completed=False
#                 )

#                 # ریست تلاش‌های چالش
#                 ChallengeAttempt.objects.filter(
#                     user=request.user,
#                     content=challenge_content
#                 ).delete()

#                 # پیام قفل شدن
#                 return Response({
#                     "is_correct": False,
#                     "message": "You've used all attempts. Review previous sections.",
#                     "attempts_remaining": 0,
#                     "sections_locked": [section.order_number, section.order_number - 1],
#                     "progress_reset": True
#                 }, status=status.HTTP_200_OK)
#             except:
#                 pass

#         # 🔹 اگر هنوز تلاش باقی داره
#         return Response({
#             "is_correct": False,
#             "message": f"Challenge failed. {3 - attempt_number} attempts left.",
#             "attempts_remaining": 3 - attempt_number
#         }, status=status.HTTP_200_OK)

# class SubmitChallengeView(APIView):
#     def post(self, request, challenge_id):
#         if not request.user.is_authenticated:
#             return Response(
#                 {"error": "Authentication required."},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )

#         try:
#             challenge_content = Content.objects.get(
#                 id=challenge_id,
#                 content_type='challenge'
#             )
#         except Content.DoesNotExist:
#             return Response(
#                 {"error": "Challenge not found."},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         section = challenge_content.section  # سرفصل فعلی (چالش)
#         course = section.course

#         # گرفتن سرفصل‌های قبلی
#         try:
#             guide_section = Section.objects.get(
#                 course=course,
#                 order_number=section.order_number - 1
#             )  # کارت راهنما
#         except Section.DoesNotExist:
#             guide_section = None

#         try:
#             video_section = Section.objects.get(
#                 course=course,
#                 order_number=section.order_number - 2
#             )  # ویدیو
#         except Section.DoesNotExist:
#             video_section = None
        
#         try:
#             video_section_next = Section.objects.get(
#                 course=course,
#                 order_number=section.order_number + 1
#             )  # ویدیو
#         except Section.DoesNotExist:
#             video_section_next = None

#         # دیسیریالایز و اعتبارسنجی پاسخ
#         serializer = SubmitChallengeSerializer(
#             data=request.data,
#             context={'challenge_data': challenge_content.challenge_data}  # ⬅️ این خط رو حتماً داشته باش
#         )
#         if not serializer.is_valid():
#             return Response(
#                 {"error": "Invalid input."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         user_answers = serializer.validated_data['answers']
#         challenge_data = challenge_content.challenge_data

#         # ارزیابی پاسخ با هوش مصنوعی
#         is_correct = evaluate_answer_with_ai(
#             challenge_data=challenge_data,
#             user_answers=user_answers
#         )

#         # ثبت تلاش
#         attempt_number = ChallengeAttempt.objects.filter(
#             user=request.user,
#             content=challenge_content
#         ).count() + 1

#         ChallengeAttempt.objects.create(
#             user=request.user,
#             content=challenge_content,
#             attempt_number=attempt_number,
#             is_successful=is_correct
#         )

#         # 🔹 اگر پاسخ درست بود
#         if is_correct:
#             if video_section_next:
#                 video_section_next.is_unlocked = False
#                 video_section_next.save()
#             return Response({
#                 "is_correct": True,
#                 "message": "Challenge passed! Next section unlocked.",
#                 "next_section_unlocked": True,
#                 "reset_required_video_order": video_section_next.order_number if video_section else None
#             }, status=status.HTTP_200_OK)

#         # 🔹 اگر پاسخ غلط بود و ۳ تلاش ناموفق داشته باشه
#         if attempt_number >= 3:
#             # 🔁 ریست پیشرفت ویدیو
#             if video_section:
#                 try:
#                     video_content = video_section.contents.get(content_type='video')
#                     UserContentProgress.objects.filter(
#                         user=request.user,
#                         content=video_content
#                     ).update(
#                         watched_duration=0,
#                         is_completed=False
#                     )
#                 except:
#                     pass

#             # 🔁 قفل کردن سرفصل چالش و کارت راهنما
#             # (در واقع، با ریست پیشرفت، دیگه دسترسی ندارن)
#             # if guide_section:
#             #     guide_section.is_unlocked = False
#             #     guide_section.save()

#             # if section:
#             #     section.is_unlocked = False
#             #     section.save()

#             # 🔁 پاک کردن تلاش‌های چالش
#             ChallengeAttempt.objects.filter(
#                 user=request.user,
#                 content=challenge_content
#             ).delete()

#             return Response({
#                 "is_correct": False,
#                 "message": "You've used all attempts. Review previous sections.",
#                 "attempts_remaining": 0,
#                 "locked_sections": [section.order_number, guide_section.order_number if guide_section else None],
#                 "video_progress_reset": True,
#                 "requires_video_review": True,
#                 "challenge_section_order": section.order_number
#             }, status=status.HTTP_200_OK)

#         # 🔹 اگر هنوز تلاش باقی داره
#         return Response({
#             "is_correct": False,
#             "message": f"Challenge failed. {3 - attempt_number} attempts left.",
#             "attempts_remaining": 3 - attempt_number
#         }, status=status.HTTP_200_OK)

class SubmitChallengeView(APIView):
    def post(self, request, challenge_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            challenge_content = Content.objects.get(
                id=challenge_id,
                content_type='challenge'
            )
        except Content.DoesNotExist:
            return Response(
                {"error": "Challenge not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        section = challenge_content.section
        course = section.course

        try:
            guide_section = Section.objects.get(
                course=course,
                order_number=section.order_number - 1
            )
        except Section.DoesNotExist:
            guide_section = None

        try:
            video_section = Section.objects.get(
                course=course,
                order_number=section.order_number - 2
            )
        except Section.DoesNotExist:
            video_section = None

        try:
            video_section_next = Section.objects.get(
                course=course,
                order_number=section.order_number + 1
            )
        except Section.DoesNotExist:
            video_section_next = None

        # ✅ ارسال context شامل challenge_data
        serializer = SubmitChallengeSerializer(
            data=request.data,
            context={'challenge_data': challenge_content.challenge_data}  # ⬅️ این خط رو اضافه کن
        )

        if not serializer.is_valid():
            return Response(
                {"error": "Invalid input."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_answers = serializer.validated_data['answers']

        # ✅ ارزیابی پاسخ — فرض کنیم این تابع وجود داره و True/False برمی‌گردونه
        is_correct = self.evaluate_answer(challenge_content.challenge_data, user_answers)

        # ✅ ثبت تلاش — is_successful حتماً مقدار می‌گیره
        attempt_number = ChallengeAttempt.objects.filter(
            user=request.user,
            content=challenge_content
        ).count() + 1

        ChallengeAttempt.objects.create(
            user=request.user,
            content=challenge_content,
            attempt_number=attempt_number,
            is_successful=is_correct  # ✅ اینجا حتماً True یا False است
        )

        # 🔹 اگر پاسخ درست بود
        if is_correct:
            if video_section_next:
                video_section_next.is_unlocked = False
                video_section_next.save()
            return Response({
                "is_correct": True,
                "message": "Challenge passed! Next section unlocked.",
                "next_section_unlocked": True,
                "reset_required_video_order": video_section_next.order_number if video_section_next else None
            }, status=status.HTTP_200_OK)

        # 🔹 اگر ۳ بار اشتباه جواب داده
        if attempt_number >= 3:
            if video_section:
                try:
                    video_content = video_section.contents.get(content_type='video')
                    UserContentProgress.objects.filter(
                        user=request.user,
                        content=video_content
                    ).update(
                        watched_duration=0,
                        is_completed=False
                    )
                except:
                    pass

            ChallengeAttempt.objects.filter(
                user=request.user,
                content=challenge_content
            ).delete()

            return Response({
                "is_correct": False,
                "message": "You've used all attempts. Review previous sections.",
                "attempts_remaining": 0,
                "locked_sections": [section.order_number, guide_section.order_number if guide_section else None],
                "video_progress_reset": True,
                "requires_video_review": True,
                "challenge_section_order": section.order_number
            }, status=status.HTTP_200_OK)

        # 🔹 اگر هنوز تلاش باقی داره
        return Response({
            "is_correct": False,
            "message": f"Challenge failed. {3 - attempt_number} attempts left.",
            "attempts_remaining": 3 - attempt_number
        }, status=status.HTTP_200_OK)

    def evaluate_answer(self, challenge_data, user_answers):
        """
        بدون هوش مصنوعی — منطق داخلی
        """
        q_type = challenge_data.get("type")
        if not q_type:
            return False

        if q_type == "multiple_choice_single":
            return user_answers == [challenge_data.get("correct_option")]

        elif q_type == "multiple_choice_multiple":
            return sorted(user_answers) == sorted(challenge_data.get("correct_options", []))

        elif q_type == "drag_drop_table":
            correct_columns = challenge_data.get("columns", [])
            if len(user_answers) != len(correct_columns):
                return False
            for col in correct_columns:
                user_col = next((uc for uc in user_answers if uc["title"] == col["title"]), None)
                if not user_col or set(user_col["options"]) != set(col["options"]):
                    return False
            return True

        elif q_type == "image_based_mcq":
            sub_questions = challenge_data.get("sub_questions", [])
            for sq in sub_questions:
                q = sq["question"]
                correct = sq["correct_option"]
                if user_answers.get(q) != str(correct):
                    return False
            return True

        elif q_type == "descriptive":
            sub_questions = challenge_data.get("sub_questions", [])
            for sq in sub_questions:
                q = sq["question"]
                correct_answer = sq["answer"].lower()
                user_answer = user_answers.get(q, "").lower()
                correct_words = set(correct_answer.split())
                user_words = set(user_answer.split())
                if not correct_words:
                    continue
                match_ratio = len(correct_words & user_words) / len(correct_words)
                if match_ratio < 0.6:
                    return False
            return True

        return False