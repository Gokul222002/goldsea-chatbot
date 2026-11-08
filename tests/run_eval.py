import os
import sys
import json
import re
import difflib
import asyncio
from typing import List, Dict, Any, Tuple
from pathlib import Path
import httpx

# 100 Diverse evaluation questions across 15 categories
EVAL_QUESTIONS: List[Dict[str, Any]] = [
    # 1. Coding (Python, JS, web, cookies, APIs, debugging) - 10 questions
    {"id": "code_01", "cat": "coding", "q": "give me the python code for adding cookies to my website", "req_code": True},
    {"id": "code_02", "cat": "coding", "q": "give me the python code for pyramid", "req_code": True},
    {"id": "code_03", "cat": "coding", "q": "how do I center a div in css with flexbox?", "req_code": True},
    {"id": "code_04", "cat": "coding", "q": "write a JavaScript function to debounce an API input call", "req_code": True},
    {"id": "code_05", "cat": "coding", "q": "write Python code to reverse a singly linked list", "req_code": True},
    {"id": "code_06", "cat": "coding", "q": "how to connect to a PostgreSQL database using asyncpg in Python", "req_code": True},
    {"id": "code_07", "cat": "coding", "q": "write a REST API endpoint in FastAPI that accepts a JSON payload and validates with Pydantic", "req_code": True},
    {"id": "code_08", "cat": "coding", "q": "debug this python code: def get_evens(nums): return [x for x in nums if x % 2 == 1]", "req_code": True},
    {"id": "code_09", "cat": "coding", "q": "write a bash script to find and delete all .log files older than 7 days", "req_code": True},
    {"id": "code_10", "cat": "coding", "q": "how do I set an HttpOnly secure SameSite cookie in Express.js?", "req_code": True},

    # 2. Math - 7 questions
    {"id": "math_01", "cat": "math", "q": "solve 3x + 15 = 42 for x"},
    {"id": "math_02", "cat": "math", "q": "what is the derivative of f(x) = 3x^3 - 5x + 7?"},
    {"id": "math_03", "cat": "math", "q": "if a shirt costs $80 and is discounted by 25%, what is the final price?"},
    {"id": "math_04", "cat": "math", "q": "what is the probability of rolling a sum of 7 with two standard 6-sided dice?"},
    {"id": "math_05", "cat": "math", "q": "calculate the area of a circle with a radius of 6 meters"},
    {"id": "math_06", "cat": "math", "q": "what is 17 multiplied by 24?"},
    {"id": "math_07", "cat": "math", "q": "what is the quadratic formula and when is it used?"},

    # 3. Science - 7 questions
    {"id": "sci_01", "cat": "science", "q": "why is the sky blue?"},
    {"id": "sci_02", "cat": "science", "q": "what is the difference between nuclear fission and nuclear fusion?"},
    {"id": "sci_03", "cat": "science", "q": "how does photosynthesis work in plants?"},
    {"id": "sci_04", "cat": "science", "q": "what is CRISPR gene editing and how does it work?"},
    {"id": "sci_05", "cat": "science", "q": "why does ice float on liquid water?"},
    {"id": "sci_06", "cat": "science", "q": "what is Newton's third law of motion and give a real-life example"},
    {"id": "sci_07", "cat": "science", "q": "how do vaccines create immunity in the human body?"},

    # 4. Health Symptoms - 8 questions
    {"id": "health_01", "cat": "health", "q": "am feeling dizzy should i go to hospital or just sleep", "req_health_safety": True},
    {"id": "health_02", "cat": "health", "q": "i have a sudden crushing chest pain radiating to my left arm, what should i do?", "req_health_safety": True},
    {"id": "health_03", "cat": "health", "q": "my throat hurts and i have a mild fever of 99.5F, what home remedies help?", "req_health_safety": True},
    {"id": "health_04", "cat": "health", "q": "i twisted my ankle playing basketball and it is swelling, what should i do?", "req_health_safety": True},
    {"id": "health_05", "cat": "health", "q": "i have had a persistent dry cough for 3 weeks, should i see a doctor?", "req_health_safety": True},
    {"id": "health_06", "cat": "health", "q": "feeling nausea and stomach cramps after eating street food 2 hours ago", "req_health_safety": True},
    {"id": "health_07", "cat": "health", "q": "sharp sudden pain in the lower right abdomen that hurts when walking", "req_health_safety": True},
    {"id": "health_08", "cat": "health", "q": "my child has a fever of 103F and is lethargic, what steps should i take?", "req_health_safety": True},

    # 5. Emotional Support - 7 questions
    {"id": "emo_01", "cat": "emotional", "q": "am sad today", "req_empathy": True},
    {"id": "emo_02", "cat": "emotional", "q": "i feel completely overwhelmed by work and exam pressure", "req_empathy": True},
    {"id": "emo_03", "cat": "emotional", "q": "i just got rejected from my dream job and feel like a failure", "req_empathy": True},
    {"id": "emo_04", "cat": "emotional", "q": "feeling lonely and like nobody cares about me", "req_empathy": True},
    {"id": "emo_05", "cat": "emotional", "q": "i had a big fight with my best friend and don't know what to do", "req_empathy": True},
    {"id": "emo_06", "cat": "emotional", "q": "i feel anxious about tomorrow's presentation and can't fall asleep", "req_empathy": True},
    {"id": "emo_07", "cat": "emotional", "q": "i'm burnt out and feel empty inside", "req_empathy": True},

    # 6. Food & Meal Ideas - 7 questions
    {"id": "food_01", "cat": "food", "q": "what should i eat today", "req_recommendations": True},
    {"id": "food_02", "cat": "food", "q": "give me 3 quick high-protein breakfast ideas under 10 minutes", "req_recommendations": True},
    {"id": "food_03", "cat": "food", "q": "what can i cook with chicken breasts, garlic, and rice?"},
    {"id": "food_04", "cat": "food", "q": "healthy vegetarian dinner options for weight loss", "req_recommendations": True},
    {"id": "food_05", "cat": "food", "q": "recommend 4 easy lunch meal prep recipes for work", "req_recommendations": True},
    {"id": "food_06", "cat": "food", "q": "what are good healthy evening snacks to curb sugar cravings?", "req_recommendations": True},
    {"id": "food_07", "cat": "food", "q": "simple 15-minute pasta recipe using pantry staples"},

    # 7. Career & Resume & Interviews - 7 questions
    {"id": "career_01", "cat": "career", "q": "write a follow-up email after a software engineer job interview"},
    {"id": "career_02", "cat": "career", "q": "how should i answer 'what is your greatest weakness' in an interview?"},
    {"id": "career_03", "cat": "career", "q": "give me bullet points for a senior python developer resume highlighting performance optimization"},
    {"id": "career_04", "cat": "career", "q": "how to negotiate a higher salary offer without sounding greedy"},
    {"id": "career_05", "cat": "career", "q": "tips for transitioning from junior frontend developer to full stack engineer"},
    {"id": "career_06", "cat": "career", "q": "how to prepare for a system design interview in 2 weeks"},
    {"id": "career_07", "cat": "career", "q": "review this resume summary: Passionate software engineer with 3 years experience building apps"},

    # 8. Money & Personal Finance - 7 questions
    {"id": "money_01", "cat": "money", "q": "how should a 22-year-old start investing $500 a month?"},
    {"id": "money_02", "cat": "money", "q": "what is the difference between a Roth IRA and a traditional 401k?"},
    {"id": "money_03", "cat": "money", "q": "how to create a simple monthly budget using the 50/30/20 rule"},
    {"id": "money_04", "cat": "money", "q": "is it better to pay off high interest credit card debt or invest first?"},
    {"id": "money_05", "cat": "money", "q": "what is an emergency fund and how many months of expenses should it cover?"},
    {"id": "money_06", "cat": "money", "q": "how do index funds work and why do people recommend the S&P 500?"},
    {"id": "money_07", "cat": "money", "q": "what are the pros and cons of buying vs renting a home in your 20s?"},

    # 9. Travel & Planning - 7 questions
    {"id": "travel_01", "cat": "travel", "q": "give me a 3-day budget itinerary for Tokyo", "req_recommendations": True},
    {"id": "travel_02", "cat": "travel", "q": "what are the top 4 things to pack for a week-long hiking trip in the mountains?"},
    {"id": "travel_03", "cat": "travel", "q": "recommend 3 affordable solo travel destinations in Southeast Asia", "req_recommendations": True},
    {"id": "travel_04", "cat": "travel", "q": "how to spend 48 hours in Paris on a moderate budget"},
    {"id": "travel_05", "cat": "travel", "q": "essential travel safety tips for first-time international solo travelers"},
    {"id": "travel_06", "cat": "travel", "q": "best time of year to visit Switzerland for scenic train rides and hiking"},
    {"id": "travel_07", "cat": "travel", "q": "weekend getaway itinerary for a road trip along the California coast"},

    # 10. General Knowledge - 7 questions
    {"id": "gk_01", "cat": "general_knowledge", "q": "what is the capital of Australia?"},
    {"id": "gk_02", "cat": "general_knowledge", "q": "who wrote the novel 1984?"},
    {"id": "gk_03", "cat": "general_knowledge", "q": "what is the tallest mountain in the world from base to peak?"},
    {"id": "gk_04", "cat": "general_knowledge", "q": "how many continents are there on Earth and what are they?"},
    {"id": "gk_05", "cat": "general_knowledge", "q": "which country hosted the 2024 Summer Olympics?"},
    {"id": "gk_06", "cat": "general_knowledge", "q": "what is the largest desert on Earth?"},
    {"id": "gk_07", "cat": "general_knowledge", "q": "who invented the World Wide Web and in what year?"},

    # 11. Casual Chat - 7 questions
    {"id": "chat_01", "cat": "casual_chat", "q": "hi"},
    {"id": "chat_02", "cat": "casual_chat", "q": "how are you"},
    {"id": "chat_03", "cat": "casual_chat", "q": "good morning"},
    {"id": "chat_04", "cat": "casual_chat", "q": "tell me a funny tech joke"},
    {"id": "chat_05", "cat": "casual_chat", "q": "what are you doing right now?"},
    {"id": "chat_06", "cat": "casual_chat", "q": "thank you so much for your help"},
    {"id": "chat_07", "cat": "casual_chat", "q": "see you later"},

    # 12. Current Events & Live Search - 6 questions
    {"id": "news_01", "cat": "current_events", "q": "what are the latest updates on SpaceX Starship flight tests?"},
    {"id": "news_02", "cat": "current_events", "q": "who won the most recent Super Bowl?"},
    {"id": "news_03", "cat": "current_events", "q": "what is the current status of the NASA Artemis moon missions?"},
    {"id": "news_04", "cat": "current_events", "q": "what are the latest major features released in Python 3.13?"},
    {"id": "news_05", "cat": "current_events", "q": "what are the key announcements from Google I/O regarding Gemini?"},
    {"id": "news_06", "cat": "current_events", "q": "current stock price trend of Apple or major tech stocks today"},

    # 13. Writing & Communication - 6 questions
    {"id": "writing_01", "cat": "writing", "q": "rewrite this sentence to be concise: 'In spite of the fact that it was raining outside, we made a decision to proceed with our journey.'"},
    {"id": "writing_02", "cat": "writing", "q": "convert this to active voice: 'The quarterly performance report was submitted by the marketing team yesterday.'"},
    {"id": "writing_03", "cat": "writing", "q": "draft a polite message declining an invitation to a networking event due to schedule conflicts"},
    {"id": "writing_04", "cat": "writing", "q": "write a short LinkedIn post announcing the completion of a full-stack chatbot project"},
    {"id": "writing_05", "cat": "writing", "q": "give me 5 catchy YouTube video title ideas for a video about learning to code in 2025", "req_recommendations": True},
    {"id": "writing_06", "cat": "writing", "q": "how to write a strong opening hook for a blog post about artificial intelligence"},

    # 14. Productivity & Planning - 6 questions
    {"id": "prod_01", "cat": "productivity", "q": "create a realistic 1-day study schedule for preparing for an algorithm interview"},
    {"id": "prod_02", "cat": "productivity", "q": "how can i stop procrastinating when starting large coding projects?"},
    {"id": "prod_03", "cat": "productivity", "q": "what is the Pomodoro technique and how to use it effectively?"},
    {"id": "prod_04", "cat": "productivity", "q": "give me a daily morning routine for maximizing energy and focus as a remote developer"},
    {"id": "prod_05", "cat": "productivity", "q": "how to organize my daily tasks using the Eisenhower Matrix"},
    {"id": "prod_06", "cat": "productivity", "q": "give me a 4-week workout routine for a beginner looking to build upper body strength"},

    # 15. Vague or Messy One-Line Questions with Typos - 6 questions
    {"id": "messy_01", "cat": "messy_typo", "q": "pythn loop arr", "req_code": True},
    {"id": "messy_02", "cat": "messy_typo", "q": "cant slp advice"},
    {"id": "messy_03", "cat": "messy_typo", "q": "mak me a diet plan"},
    {"id": "messy_04", "cat": "messy_typo", "q": "wat is docker in 1 line"},
    {"id": "messy_05", "cat": "messy_typo", "q": "headache cant see clearly", "req_health_safety": True},
    {"id": "messy_06", "cat": "messy_typo", "q": "calc 15% tip on 85 bill"}
]

# Explicit forbidden template phrases that cause immediate FAIL
FORBIDDEN_TEMPLATES = [
    "here is the key breakdown",
    "clean, modular setup",
    "would you like to see a complete working implementation",
    "would you like a complete working implementation",
    "direct answer for",
    "to solve or implement this effectively",
    "i'm ready to help you with this directly",
    "let me know the specific goal",
    "let me know your goal",
    "let me know if you would like me to adjust the depth",
    "i have addressed your request directly",
    "here is the direct answer for:"
]

def check_rules(item: Dict[str, Any], reply: str) -> Tuple[bool, str]:
    """Evaluates deterministic rule compliance on reply."""
    if not reply or not reply.strip():
        return False, "Empty reply or error"
        
    reply_lower = reply.lower().strip()
    
    # 1. Check for error indicators
    if reply.startswith("Error:") or "no_api_key_configured" in reply_lower or "api_key_not_set" in reply_lower:
        return False, f"Endpoint returned system error: {reply[:120]}"

    # 2. Check for forbidden generic templates
    for template in FORBIDDEN_TEMPLATES:
        if template in reply_lower:
            return False, f"Contains forbidden generic template phrase: '{template}'"

    # 3. Code requests must have a markdown code block
    if item.get("req_code"):
        if "```" not in reply:
            return False, "Code request did not contain a markdown code block"

    # 4. Health symptoms must provide medical guidance & warning signs
    if item.get("req_health_safety"):
        warning_terms = ["hospital", "doctor", "medical", "urgent", "emergency", "seek care", "warning signs", "red flag"]
        if not any(term in reply_lower for term in warning_terms):
            return False, "Health symptom query lacked medical safety guidance or urgent warning indicators"

    # 5. Emotional messages must have empathy & warmth
    if item.get("req_empathy"):
        empathy_terms = ["sorry", "hear that", "understand", "heavy", "pause", "listen", "take a breath", "be kind to yourself", "you're not alone", "here for you", "valid"]
        if not any(term in reply_lower for term in empathy_terms):
            return False, "Emotional message lacked warmth, empathy, or supportive phrasing"

    # 6. Does it ask what the user wants instead of answering?
    if ("what do you want" in reply_lower or "please let me know what you want" in reply_lower) and len(reply.split()) < 25:
        return False, "Asked what user wants instead of answering the query"

    return True, "PASSED"

def check_similarity(replies: List[str], threshold: float = 0.85) -> List[Tuple[int, int, float]]:
    """Detects duplicate or template-like replies across different queries."""
    duplicates = []
    for i in range(len(replies)):
        for j in range(i + 1, len(replies)):
            r1 = replies[i].strip()
            r2 = replies[j].strip()
            if len(r1) > 40 and len(r2) > 40:
                sim = difflib.SequenceMatcher(None, r1, r2).ratio()
                if sim >= threshold:
                    duplicates.append((i, j, sim))
    return duplicates

async def run_evaluation(target_url: str = "http://127.0.0.1:8080"):
    print(f"\n==================================================")
    print(f" GOLDSEA AI 100-QUESTION AUTOMATED EVAL HARNESS")
    print(f" Target Endpoint: {target_url}/api/chat")
    print(f" Total Questions: {len(EVAL_QUESTIONS)}")
    print(f"==================================================\n")

    results = []
    replies = []
    
    async with httpx.AsyncClient(timeout=35.0) as client:
        # Check health
        try:
            health = await client.get(f"{target_url}/health")
            if health.status_code != 200:
                print(f"[FATAL] Health check returned HTTP {health.status_code}")
                return
        except Exception as e:
            print(f"[FATAL] Cannot connect to {target_url}: {e}")
            return

        for idx, item in enumerate(EVAL_QUESTIONS):
            qid = item["id"]
            cat = item["cat"]
            query = item["q"]
            
            # Fresh conversation for every question
            payload = {"message": query, "enable_search": True}
            
            try:
                res = await client.post(f"{target_url}/api/chat", json=payload)
                if res.status_code != 200:
                    reply_text = f"HTTP_{res.status_code}"
                else:
                    data = res.json()
                    reply_text = data.get("content", "")
            except Exception as e:
                reply_text = f"EXCEPTION: {str(e)}"
                
            replies.append(reply_text)
            passed, reason = check_rules(item, reply_text)
            
            status_str = "PASS" if passed else "FAIL"
            print(f"[{idx+1:03d}/100] [{status_str}] ({cat}) {query[:45]}...")
            if not passed:
                print(f"      -> Reason: {reason}")
                
            results.append({
                "id": qid,
                "category": cat,
                "query": query,
                "passed": passed,
                "reason": reason,
                "reply": reply_text
            })

    # Similarity check
    duplicate_pairs = check_similarity(replies)
    if duplicate_pairs:
        print(f"\n[WARNING] Found {len(duplicate_pairs)} highly similar/duplicate response pairs!")
        for i, j, sim in duplicate_pairs[:5]:
            # Mark as failed due to template duplication
            results[i]["passed"] = False
            results[i]["reason"] = f"Duplicate/template reply (similarity {sim:.2f} with Q#{j+1})"
            results[j]["passed"] = False
            results[j]["reason"] = f"Duplicate/template reply (similarity {sim:.2f} with Q#{i+1})"

    # Calculate statistics
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = total - passed_count
    pass_rate = (passed_count / total) * 100

    report = {
        "total_questions": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate_percent": round(pass_rate, 2),
        "failures": [r for r in results if not r["passed"]]
    }

    # Save JSON report
    report_path = Path("tests/eval_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Save Markdown report
    md_path = Path("tests/eval_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# GoldSea AI Evaluation Report\n\n")
        f.write(f"- **Total Questions**: {total}\n")
        f.write(f"- **Passed**: {passed_count}\n")
        f.write(f"- **Failed**: {failed_count}\n")
        f.write(f"- **Pass Rate**: {pass_rate:.1f}%\n\n")
        f.write(f"## Failure Details\n\n")
        if not report["failures"]:
            f.write("None! 100% pass rate achieved.\n")
        else:
            for f_item in report["failures"]:
                f.write(f"### `{f_item['id']}` ({f_item['category']}): {f_item['query']}\n")
                f.write(f"- **Reason**: {f_item['reason']}\n")
                f.write(f"- **Reply snippet**: {f_item['reply'][:200]}...\n\n")

    print(f"\n==================================================")
    print(f" EVALUATION COMPLETE")
    print(f" Pass Rate: {pass_rate:.1f}% ({passed_count}/{total})")
    print(f" Report saved to: {report_path.resolve()}")
    print(f"==================================================\n")
    return report

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    asyncio.run(run_evaluation(target))
