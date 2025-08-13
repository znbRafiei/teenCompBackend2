# import google.generativeai as genai
# from django.conf import settings

# def evaluate_answer_with_ai(challenge_data, user_answers):
#     """
#     ارزیابی پاسخ کاربر برای هر ۵ مدل سوال.
#     فقط از Gemini استفاده می‌کنه — بدون نیاز به ifهای پیچیده.
#     """
#     try:
#         import google.generativeai as genai
#         from django.conf import settings
#         genai.configure(api_key=settings.GEMINI_API_KEY)
#         model = genai.GenerativeModel('gemini-pro')

#         # ساخت prompt بر اساس نوع سوال
#         prompt = f"""
#         You are an expert evaluator for an online learning platform.
#         Evaluate if the user's answer is correct based on the correct answer.

#         **Challenge Data**: {challenge_data}
#         **User Answers**: {user_answers}

#         Rules:
#         - For 'multiple_choice_single': Check if the selected option ID matches the correct_option.
#         - For 'multiple_choice_multiple': Check if all selected option IDs match correct_options.
#         - For 'drag_drop_table': Check if each tool is correctly matched to its use.
#         - For 'image_based_mcq': Check if the answer to the sub-question is correct.
#         - For 'descriptive': Check if the key concepts are present and accurate.

#         Respond ONLY with 'True' if the answer is acceptable, or 'False' if it's not.
#         Do not explain. Only return True or False.
#         """

#         response = model.generate_content(prompt)
#         result = response.text.strip().lower()

#         return result == 'true'
#     except Exception as e:
#         print(f"AI Evaluation Error: {e}")
#         # فیل‌بک: اگر Gemini خطا داد، منطق ساده برای سوالات چندگزینه‌ای
#         return fallback_evaluate(challenge_data, user_answers)


# def fallback_evaluate(challenge_data, user_answers):
#     """
#     فیل‌بک برای سوالات چندگزینه‌ای ساده.
#     فقط برای اطمینان.
#     """
#     q_type = challenge_data.get("type")

#     if q_type == "multiple_choice_single":
#         return user_answers == [challenge_data.get("correct_option")]

#     elif q_type == "multiple_choice_multiple":
#         return sorted(user_answers) == sorted(challenge_data.get("correct_options", []))

#     elif q_type == "image_based_mcq":
#         sub_q = challenge_data.get("sub_questions", [])[0]
#         return user_answers == [sub_q.get("correct_option")]

#     else:
#         # برای تشریحی و جدولی، فیل‌بک نداریم — فقط Gemini
#         return False
def evaluate_answer_with_ai(challenge_data, user_answers):
    """
    بدون استفاده از هوش مصنوعی — فقط منطق داخلی برای همه ۵ مدل سوال.
    فقط و فقط این تابع جایگزین میشه — بقیه کد دست نخورده میمونه.
    """
    q_type = challenge_data.get("type")
    if not q_type:
        return False

    # 1. چندگزینه‌ای یک‌درست
    if q_type == "multiple_choice_single":
        correct = challenge_data.get("correct_option")
        if not correct:
            return False
        return user_answers == [correct]

    # 2. چندگزینه‌ای چنددرست
    elif q_type == "multiple_choice_multiple":
        correct = challenge_data.get("correct_options", [])
        if not isinstance(correct, list):
            return False
        return sorted(user_answers) == sorted(correct)

    # 3. جدولی (Drag & Drop Table)
    elif q_type == "drag_drop_table":
        # فرض: user_answers یه دیکشنری از {"Column Title": "Selected Option"} هست
        correct_columns = challenge_data.get("columns", [])
        if not correct_columns:
            return False

        # ✅ استخراج پاسخ کاربر
        if not isinstance(user_answers, list):
            return False
        if len(user_answers) != len(correct_columns):
            return False

        # ✅ مقایسه هر ستون
        for correct_col in correct_columns:
            title = correct_col.get("title")
            correct_options = set(correct_col.get("options", []))

            # پیدا کردن ستون مربوطه در پاسخ کاربر
            user_col = next((uc for uc in user_answers if uc.get("title") == title), None)
            if not user_col:
                return False

            user_options = set(user_col.get("options", []))

            # ✅ مقایسه مجموعه‌ها (ترتیب مهم نیست)
            if correct_options != user_options:
                return False

    # 4. تصویری با زیرسوال (Image-Based MCQ)
    elif q_type == "image_based_mcq":
        sub_questions = challenge_data.get("sub_questions", [])
        if not sub_questions:
            return False

        for sq in sub_questions:
            q_text = sq.get("question")
            correct_option = sq.get("correct_option")
            if not q_text or not correct_option:
                return False
            if user_answers.get(q_text) != str(correct_option):
                return False
        return True

    # 5. تشریحی با زیرسوال (Descriptive)
    elif q_type == "descriptive":
        sub_questions = challenge_data.get("sub_questions", [])
        if not sub_questions:
            return False

        for sq in sub_questions:
            q_text = sq.get("question")
            correct_answer = sq.get("answer", "").strip().lower()
            user_answer = user_answers.get(q_text, "").strip().lower()

            if not correct_answer or not user_answer:
                return False

            # ✅ استخراج کلمات کلیدی اصلی از پاسخ درست
            keywords = extract_keywords(correct_answer)

            # ✅ چک کردن وجود کلمات کلیدی در پاسخ کاربر
            if not all(keyword in user_answer for keyword in keywords):
                return False

        return True  # همه پاسخ‌ها مفهوماً درست هستن

    else:
        return False
    
def extract_keywords(text):
    """
    کلمات کلیدی اصلی رو از جمله استخراج می‌کنه.
    فقط اسم، فعل اصلی و صفت مهم رو نگه می‌داره.
    """
    # ✅ کلمات کلیدی اصلی — بدون ضمایر، حروف اضافه، افعال کمکی
    stop_words = {
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'has', 'have', 'had', 'do', 'does', 'did',
        'the', 'a', 'an', 'this', 'that', 'these', 'those',
        'in', 'on', 'at', 'by', 'with', 'for', 'to', 'of', 'and', 'or'
    }

    # تقسیم متن به کلمات
    words = text.replace('.', '').replace(',', '').split()
    keywords = [word for word in words if word not in stop_words]
    return keywords