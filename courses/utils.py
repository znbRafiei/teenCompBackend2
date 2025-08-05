from .models import Section,ChallengeAttempt

def unlock_next_sections(user, from_section, num_sections=2):
    """
    دو سرفصل بعدی یک ویدیو رو برای کاربر تعیین می‌کنه.
    این تابع فقط لیست سرفصل‌هایی که باید باز بشن رو برمی‌گردونه.
    ذخیره‌سازی در View یا Serializer انجام میشه.

    Args:
        user: کاربر فعلی
        from_section: سرفصلی که ویدیویش ۸۰٪ دیده شده
        num_sections: تعداد سرفصل‌هایی که باید بعد از این باز بشن (پیش‌فرض ۲)

    Returns:
        لیستی از شیءهای Section که باید باز بشن
    """
    course = from_section.course

    # گرفتن تمام سرفصل‌های دوره به ترتیب
    all_sections = Section.objects.filter(course=course).order_by('order_number')

    # پیدا کردن ایندکس سرفصل فعلی
    try:
        current_index = list(all_sections).index(from_section)
    except ValueError:
        return []

    # پیدا کردن سرفصل‌های بعدی (مثلاً +1 و +2)
    next_sections = []
    for i in range(1, num_sections + 1):
        next_index = current_index + i
        if next_index < len(all_sections):
            next_sections.append(all_sections[next_index])

    return next_sections

def can_access_challenge(user, challenge_content):
    """
    چک می‌کنه کاربر مجاز به حل چالش است یا نه.
    """
    try:
        attempts = ChallengeAttempt.objects.filter(
            user=user,
            content=challenge_content
        ).order_by('-submitted_at')
        attempt_count = attempts.count()
        is_successful = attempts.filter(is_successful=True).exists()

        if attempt_count < 3 and not is_successful:
            return True  # کاربر مجازه به دوباره امتحان کردن
        elif is_successful:
            return True  # کاربر چالش را حل کرده
        else:
            return False  # کاربر فرصت تمام شده
    except:
        return False