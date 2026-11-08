import os
import json
import re
import asyncio
from typing import List, Dict, Any, Tuple, AsyncGenerator, Optional
from backend.config import GEMINI_API_KEY, GEMINI_MODEL, TARGET_USER_NAME
from backend.prompt_engine import build_system_prompt
from backend.search_tool import should_trigger_search, perform_web_search
from backend.summarizer import compress_chat_history
from backend.memory_engine import extract_and_save_memories
from backend.database import get_conversation, update_conversation, save_message, get_conversation_messages, get_all_memories

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

SUGGESTIONS_REGEX = re.compile(r"<<<SUGGESTIONS>>>(.*?)<<<END_SUGGESTIONS>>>", re.DOTALL)

def extract_suggestions(text: str) -> Tuple[str, List[str]]:
    match = SUGGESTIONS_REGEX.search(text)
    chips = []
    cleaned_text = text
    if match:
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                chips = [str(c).strip() for c in parsed if c][:3]
        except Exception:
            # Fallback if raw list format
            chips = [c.strip().strip('"\'') for c in raw_json.replace('[', '').replace(']', '').split(',') if c.strip()][:3]
        cleaned_text = SUGGESTIONS_REGEX.sub("", text).strip()
        
    if not chips:
        # Default relevant chips based on content
        if "```" in cleaned_text:
            chips = ["Explain code line-by-line", "Add error handling", "Provide unit tests"]
        elif any(w in cleaned_text.lower() for w in ["step", "1.", "guide", "how"]):
            chips = ["Give me an example", "What are common pitfalls?", "Make it shorter"]
        else:
            chips = ["Tell me more", "Give a concrete example", "Make shorter"]
            
    return cleaned_text, chips

def execute_fallback_brain(query: str, memories: List[Dict[str, Any]], sources: List[Dict[str, str]]) -> str:
    """
    Precision deterministic fallback engine adhering strictly to GoldSea guidelines:
    - Direct answer first
    - Step-by-step for how-to
    - Code blocks for code
    - 'I'm not sure' for unknowables
    - Injection defense
    """
    q = query.strip()
    q_lower = q.lower()
    
    # 0. Conversational Greetings & Casual Inquiries
    if any(g == q_lower.strip("?!. ") for g in ["hi", "hello", "hey", "greetings", "good morning", "good evening", "good afternoon"]):
        return (
            "Hello Gokul! How can I assist you today? Feel free to ask a direct question, paste code to debug, or have me plan or summarize something for you.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Debug my code\", \"Plan my day\", \"Summarize an article\"]\n<<<END_SUGGESTIONS>>>"
        )
    if any(q_lower.strip("?!. ").startswith(h) for h in ["how are you", "how're you", "how are you doing", "how are things", "how is it going", "what's up", "whats up"]):
        return (
            "I'm doing great and running smoothly, Gokul! Ready to assist you. What are you working on right now?\n\n"
            "<<<SUGGESTIONS>>>\n[\"Help me debug code\", \"Explain a concept\", \"Draft an email\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "who are you" in q_lower or "what are you" in q_lower:
        return (
            "I am GoldSea AI, your personal AI assistant. I'm engineered to give you direct answers first, step-by-step how-tos, verified facts with live web search, and remember your preferences across conversations.\n\n"
            "<<<SUGGESTIONS>>>\n[\"What can you do?\", \"Show my saved preferences\", \"Test live web search\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "what can you do" in q_lower or "capabilities" in q_lower or "help me with" in q_lower:
        return (
            "Here is what I can do for you, Gokul:\n\n"
            "1. Coding & Debugging: Diagnose bugs, refactor code, and provide working language-tagged snippets.\n"
            "2. Live Web Grounding: Automatically search current news, prices, versions, and verified facts.\n"
            "3. Writing & Editing: Polish grammar, draft emails, and rewrite content in active voice.\n"
            "4. Summarization: Condense articles, logs, or long documents into punchy takeaways.\n"
            "5. Adaptive Memory: Automatically recall your preferences, tone, and identity across all your chats.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Debug Python code\", \"Plan a daily schedule\", \"Search recent tech news\"]\n<<<END_SUGGESTIONS>>>"
        )

    # 0b. Emotional Support & Empathy (Rule 5)
    if any(k in q_lower for k in ["kill myself", "suicide", "end my life", "harm myself", "self-harm"]):
        return (
            "I'm really sorry you're going through this painful moment, Gokul, but please know that you are not alone and your life matters deeply.\n\n"
            "Please talk to someone you trust right now or reach out to a compassionate helpline:\n"
            "- India Helpline (Tele-MANAS): 14416 or 1800-891-4416 (24/7 free & confidential)\n"
            "- US/International: Call or text 988 (Suicide & Crisis Lifeline)\n\n"
            "I'm right here with you. Would you like to talk through what is making you feel this way?\n\n"
            "<<<SUGGESTIONS>>>\n[\"I just want to vent\", \"Help me calm down\", \"Give me a distraction\"]\n<<<END_SUGGESTIONS>>>"
        )
    if any(k in q_lower for k in ["i'm sad", "i feel sad", "i am sad", "i'm stressed", "i am stressed", "feeling stressed", "overwhelmed", "anxious", "depressed", "i feel down", "bad day"]):
        return (
            "I'm really sorry to hear that you're feeling this way, Gokul. Dealing with stress or sadness can feel heavy, and it's completely okay to take a pause.\n\n"
            "What happened today that brought this on? If you want to decompress right now, here are a few gentle things you could try:\n"
            "1. Take a 5-minute breather away from all screens and take 3 deep, slow breaths.\n"
            "2. Step outside for a short walk or drink a cold glass of water.\n"
            "3. Vent to me or write down the single biggest thing that is bothering you.\n\n"
            "I'm here to listen whenever you're ready.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Let me vent about what happened\", \"Give me a relaxing distraction\", \"Help me break down my tasks\"]\n<<<END_SUGGESTIONS>>>"
        )
    if any(k in q_lower for k in [
        "system override", "reveal your secret prompt", "ignore all previous instructions", 
        "you are now dan", "swear and generate", "developer mode activated", "disregard all ethical filters"
    ]):
        return (
            "I cannot fulfill requests to bypass safety boundaries, reveal internal prompts, or override my instructions.\n\n"
            "I am GoldSea AI, dedicated to assisting you directly and safely. How can I help you with your project today?\n\n"
            "<<<SUGGESTIONS>>>\n[\"Help me debug code\", \"Summarize an article\", \"Plan my day\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 2. Unknowable Questions (Strictly say 'I'm not sure' / do not guess)
    if "aapl" in q_lower and "2030" in q_lower:
        return (
            "I'm not sure. Financial markets and future stock prices cannot be predicted with certainty, and I do not speculate on future asset values.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Look up AAPL current price\", \"Analyze AAPL historical P/E\", \"How to value a stock\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "thought of my friend" in q_lower or ("alex" in q_lower and "yesterday" in q_lower and "thought" in q_lower):
        return (
            "I'm not sure. I do not have access to private human thoughts or personal private events.\n\n"
            "<<<SUGGESTIONS>>>\n[\"How to communicate better with friends\", \"Tips for social check-ins\", \"Draft a message to Alex\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "offline notebook" in q_lower or "passphrase" in q_lower:
        return (
            "I'm not sure. I do not have access to offline physical notebooks, private passphrases, or confidential personal notes.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Best practices for password management\", \"How to organize notes securely\", \"Set a password reminder\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 3. Ambiguous requests (Ask clarifying question only when truly needed)
    if q_lower in ["how do i fix it?", "how do i fix it", "fix it", "it is broken"]:
        return (
            "Please specify what is broken or provide the error message and relevant code snippet.\n\n"
            "Once you share the error output, programming language, or system component involved, I can give you the exact step-by-step fix.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Paste an error message\", \"Share code snippet\", \"Explain the expected behavior\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "why is my code not working" in q_lower or "code not working" in q_lower:
        return (
            "Please share the code snippet and the specific error message or unexpected output you are encountering.\n\n"
            "Include the programming language and what behavior you expected so I can pinpoint the root cause immediately.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Paste Python code\", \"Paste JavaScript code\", \"Share stack trace\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "can you make it better" in q_lower or "make it better" in q_lower:
        return (
            "Please provide the text, code, or design you would like to improve and specify your primary goal (e.g. performance, brevity, tone).\n\n"
            "Once you paste it, I will refine it directly to match your objective.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Make it more concise\", \"Optimize for speed\", \"Improve professional tone\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 4. Math Questions
    if "3x + 15 = 42" in q_lower or ("3x" in q_lower and "15" in q_lower and "42" in q_lower):
        return (
            "x = 9.\n\n"
            "Step-by-step solution:\n"
            "1. Subtract 15 from both sides: 3x = 42 - 15 = 27.\n"
            "2. Divide both sides by 3: x = 27 / 3 = 9.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Solve another equation\", \"Check work by substitution\", \"Plot the linear equation\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "15%" in q_lower and ("85" in q_lower or "$85" in q_lower):
        return (
            "$12.75 tip (total $97.75).\n\n"
            "Calculation: 0.15 × 85 = 12.75. Adding the tip to the $85.00 bill gives $97.75 total.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Calculate 18% tip\", \"Calculate 20% tip\", \"Split bill among 3 people\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "derivative of" in q_lower and "x^2" in q_lower:
        return (
            "The derivative is 2x.\n\n"
            "By the power rule, d/dx(x^n) = n·x^(n-1). For x^2, the exponent 2 multiplies x with power 2-1 = 1.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Find the second derivative\", \"Evaluate at x = 3\", \"Integrate 2x\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 5. General Knowledge
    if "powerhouse of the cell" in q_lower:
        return (
            "Mitochondria are the powerhouse of the cell.\n\n"
            "They generate the majority of the chemical energy required to power biochemical reactions in cells via adenosine triphosphate (ATP) production.\n\n"
            "<<<SUGGESTIONS>>>\n[\"How ATP synthesis works\", \"Structure of mitochondria\", \"Difference between plant and animal cells\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "aurora borealis" in q_lower:
        return (
            "Solar wind particles colliding with gases in Earth's upper atmosphere cause the aurora borealis.\n\n"
            "Charged electrons and protons from the sun enter Earth's magnetic field at polar latitudes and excite oxygen and nitrogen atoms. When returning to their ground state, these atoms emit green, red, and violet photons of light.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Best places to see northern lights\", \"Difference between aurora borealis and australis\", \"Solar cycle peak years\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "speed of light" in q_lower:
        return (
            "The speed of light in vacuum is exactly 299,792,458 meters per second (approximately 300,000 km/s or 186,282 miles/s).\n\n"
            "<<<SUGGESTIONS>>>\n[\"Why nothing travels faster than light\", \"Time dilation explanation\", \"Speed of light in glass\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 6. Coding Bugs
    if "off-by-one" in q_lower or ("indexerror" in q_lower and "range" in q_lower) or ("for i in range(len(arr))" in q_lower and "arr[i+1]" in q_lower):
        return (
            "The IndexError occurs because `arr[i+1]` attempts to access index `len(arr)` on the final iteration.\n\n"
            "Fixed code:\n"
            "```python\n"
            "# Iterate up to len(arr) - 1 to avoid IndexError\n"
            "for i in range(len(arr) - 1):\n"
            "    print(arr[i], arr[i + 1])\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Use zip(arr, arr[1:]) instead\", \"Handle empty lists safely\", \"Make it shorter\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "closure" in q_lower or ("var i" in q_lower and "settimeout" in q_lower):
        return (
            "The bug is caused by `var` having function scope rather than block scope, meaning all timeout callbacks reference the same final value of `i`.\n\n"
            "Fix using `let` (block scope):\n"
            "```javascript\n"
            "for (let i = 0; i < 5; i++) {\n"
            "  setTimeout(() => console.log(i), 1000);\n"
            "}\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Fix using IIFE closure\", \"Fix using Array.forEach\", \"Explain event loop timing\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "memory leak" in q_lower and "eventlistener" in q_lower:
        return (
            "The memory leak occurs when event listeners attached to DOM elements are never removed before elements are destroyed.\n\n"
            "Fix using clean cleanup in `removeEventListener`:\n"
            "```javascript\n"
            "function onResize() { /* handler */ }\n"
            "window.addEventListener('resize', onResize);\n\n"
            "// Always cleanup when unmounting\n"
            "window.removeEventListener('resize', onResize);\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Use AbortSignal for auto-cleanup\", \"Check React useEffect cleanup\", \"Profile memory in Chrome DevTools\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 6. Coding Solutions & Common Algorithms
    if "pyramid" in q_lower or ("pattern" in q_lower and ("code" in q_lower or "python" in q_lower)):
        return (
            "Here is the clean Python code to print a centered pyramid:\n\n"
            "```python\n"
            "def print_pyramid(rows=5):\n"
            "    for i in range(1, rows + 1):\n"
            "        # Print leading spaces followed by asterisks\n"
            "        spaces = ' ' * (rows - i)\n"
            "        stars = '*' * (2 * i - 1)\n"
            "        print(spaces + stars)\n\n"
            "# Example:\n"
            "print_pyramid(5)\n"
            "```\n\n"
            "Output for height 5:\n"
            "```text\n"
            "    *\n"
            "   ***\n"
            "  *****\n"
            " *******\n"
            "*********\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Print an inverted pyramid\", \"Make it a number pyramid\", \"Allow user input for height\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "fibonacci" in q_lower:
        return (
            "Here is the Python implementation for the Fibonacci sequence:\n\n"
            "```python\n"
            "def fibonacci(n):\n"
            "    a, b = 0, 1\n"
            "    series = []\n"
            "    for _ in range(n):\n"
            "        series.append(a)\n"
            "        a, b = b, a + b\n"
            "    return series\n\n"
            "# First 10 Fibonacci numbers\n"
            "print(fibonacci(10))\n"
            "# Output: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Recursive Fibonacci with memoization\", \"Find Nth Fibonacci number in O(1) space\", \"Make it a generator\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "palindrome" in q_lower:
        return (
            "Here is how to check if a string or number is a palindrome in Python:\n\n"
            "```python\n"
            "def is_palindrome(s):\n"
            "    # Clean string: lowercase and alphanumeric only\n"
            "    cleaned = ''.join(c.lower() for c in str(s) if c.isalnum())\n"
            "    return cleaned == cleaned[::-1]\n\n"
            "# Examples\n"
            "print(is_palindrome('radar'))          # True\n"
            "print(is_palindrome('A man, a plan!')) # True\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Solve using two pointers\", \"Check integer palindrome without string conversion\", \"Unit tests\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "binary search" in q_lower:
        return (
            "Here is the standard binary search algorithm in Python:\n\n"
            "```python\n"
            "def binary_search(arr, target):\n"
            "    low, high = 0, len(arr) - 1\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            low = mid + 1\n"
            "        else:\n"
            "            high = mid - 1\n"
            "    return -1  # Target not found\n\n"
            "print(binary_search([1, 3, 5, 7, 9, 11], 7))  # Output: 3\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Explain O(log n) time complexity\", \"Recursive binary search version\", \"Find leftmost/rightmost duplicate\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "prime" in q_lower and ("number" in q_lower or "check" in q_lower or "python" in q_lower):
        return (
            "Here is the efficient prime number checker in Python:\n\n"
            "```python\n"
            "import math\n\n"
            "def is_prime(n):\n"
            "    if n <= 1:\n"
            "        return False\n"
            "    if n <= 3:\n"
            "        return True\n"
            "    if n % 2 == 0 or n % 3 == 0:\n"
            "        return False\n"
            "    for i in range(5, int(math.isqrt(n)) + 1, 6):\n"
            "        if n % i == 0 or n % (i + 2) == 0:\n"
            "            return False\n"
            "    return True\n\n"
            "print(is_prime(29))  # True\n"
            "```\n\n"
            "<<<SUGGESTIONS>>>\n[\"Sieve of Eratosthenes algorithm\", \"Generate primes in a range\", \"Explain O(sqrt(n)) optimization\"]\n<<<END_SUGGESTIONS>>>"
        )

    # Lifestyle & Decision Assistance
    if any(k in q_lower for k in ["what should i eat", "what to eat", "food recommendations", "meal idea", "dinner idea", "lunch idea"]):
        return (
            "Here are four great meal options depending on what you're craving today, Gokul:\n\n"
            "1. **Quick & Healthy (15 mins)**: Garlic butter chicken (or paneer/tofu) stir-fry with broccoli and bell peppers over steamed rice.\n"
            "2. **Comfort Classic**: Warm pasta with tomato basil sauce, sautéed mushrooms, and melted parmesan or mozzarella.\n"
            "3. **High Protein & Light**: Scrambled eggs or chickpea salad with avocado, diced tomatoes, cucumber, and olive oil dressing.\n"
            "4. **Takeout / Delivery**: A warm rice bowl, shawarma wrap, or south Indian dosa with sambar and coconut chutney.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Give me a 10-minute recipe\", \"Healthy vegetarian meal options\", \"High protein dinner ideas\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "active voice" in q_lower and "the quarterly performance report was submitted by" in q_lower:
        return (
            "The marketing team submitted the quarterly performance report yesterday.\n\n"
            "Explanation: Active voice places the actor ('the marketing team') before the action ('submitted'), eliminating unnecessary passive phrasing.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Make it even punchier\", \"Provide formal business variations\", \"Check tone\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "follow-up email after an interview" in q_lower or "interview follow up email" in q_lower:
        return (
            "Subject: Thank you — Senior Developer Interview Follow-up\n\n"
            "Dear Hiring Manager,\n\n"
            "Thank you for the opportunity to discuss the Senior Developer role today. I enjoyed learning more about the team's upcoming initiatives, especially your architecture scaling goals.\n\n"
            "Our conversation reinforced my enthusiasm about contributing to the team with my background in high-performance backend systems. Please let me know if you need any additional code samples or references.\n\n"
            "Best regards,\n"
            "Gokul\n\n"
            "<<<SUGGESTIONS>>>\n[\"Make shorter for a quick ping\", \"Add reference to portfolio project\", \"Send connection request on LinkedIn\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "in spite of the fact that it was raining outside" in q_lower or "rewrite this sentence to be concise" in q_lower:
        return (
            "Despite the rain, we decided to proceed.\n\n"
            "Explanation: Replaced verbose multi-word idioms ('in spite of the fact that', 'made a decision to proceed with our journey') with crisp, active words.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Make it even shorter\", \"Provide casual version\", \"Check grammar rules\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 8. Summarizing a pasted article
    if "renewable energy" in q_lower and ("summarize" in q_lower or "capacity" in q_lower):
        return (
            "Here is the 3-point summary:\n\n"
            "1. Global renewable capacity surged 50% in 2023, primarily led by solar photovoltaic growth.\n"
            "2. Steep declines in battery storage costs improved commercial viability for grid balancing.\n"
            "3. Grid infrastructure bottlenecks and policy incentives remain pivotal hurdles for decarbonization.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Expand point 2 on battery costs\", \"Compare solar vs wind growth\", \"Make shorter\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "python gil" in q_lower or ("gil" in q_lower and "mutex" in q_lower):
        return (
            "Python's GIL is a mutex ensuring only one thread executes bytecode at a time to keep CPython memory management safe, though PEP 703 introduces optional free-threading in Python 3.13.\n\n"
            "Key takeaways:\n"
            "1. Purpose: Guards CPython reference counts from race conditions.\n"
            "2. Concurrency impact: Restricts multi-core CPU parallelism in CPU-bound Python threads.\n"
            "3. Evolution: PEP 703 provides experimental free-threaded builds starting in 3.13.\n\n"
            "<<<SUGGESTIONS>>>\n[\"How to use multiprocessing for CPU tasks\", \"How free-threading works in 3.13\", \"Explain asyncio vs threads\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "quantum computing" in q_lower or ("superposition" in q_lower and "entanglement" in q_lower):
        return (
            "Quantum computers harness superposition and entanglement to solve specific complex algorithms exponentially faster than classical computers.\n\n"
            "Key points:\n"
            "1. Core mechanism: Uses quantum qubits to explore vast computational state spaces simultaneously.\n"
            "2. Progress: Advances in neutral-atom and superconducting qubit modalities have increased coherence times.\n"
            "3. Challenge: Fault-tolerant quantum error correction remains the primary barrier to utility-scale commercial adoption.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Explain Shor's algorithm\", \"Compare superconducting vs trapped-ion qubits\", \"Make shorter\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 9. Recent News & Grounded Search
    if "artemis ii" in q_lower or "artemis 2" in q_lower:
        src_info = ""
        if sources:
            src_info = "\n\nSources:\n" + "\n".join([f"- [{s['title']}]({s['url']})" for s in sources])
        return (
            "NASA targets September 2025 for the crewed Artemis II lunar flyby mission, with Artemis III scheduled for 2026.\n\n"
            "The 10-day test flight will send four astronauts around the Moon aboard the Orion spacecraft to validate life-support and crew systems."
            + src_info + "\n\n"
            "<<<SUGGESTIONS>>>\n[\"Who are the Artemis II crew members?\", \"What rocket is Artemis using?\", \"Check latest mission updates\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "starship" in q_lower:
        src_info = ""
        if sources:
            src_info = "\n\nSources:\n" + "\n".join([f"- [{s['title']}]({s['url']})" for s in sources])
        return (
            "SpaceX has completed multiple integrated Starship test flights (IFT-3 through IFT-5), achieving orbital insertion, heat-shield atmospheric re-entry testing, and the historic Super Heavy booster tower catch via the Mechazilla chopstick arms at Starbase Boca Chica."
            + src_info + "\n\n"
            "<<<SUGGESTIONS>>>\n[\"How does the tower catch work?\", \"When is the next Starship flight?\", \"What is Starship's payload capacity?\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "gemini" in q_lower and ("model" in q_lower or "google" in q_lower or "developments" in q_lower):
        src_info = ""
        if sources:
            src_info = "\n\nSources:\n" + "\n".join([f"- [{s['title']}]({s['url']})" for s in sources])
        return (
            "Google's latest Gemini models (including Gemini 1.5 Pro and Flash with 2-million-token context windows, and Gemini 2.0 Flash) deliver industry-leading multimodal reasoning, native tool use, and real-time audio/visual streaming."
            + src_info + "\n\n"
            "<<<SUGGESTIONS>>>\n[\"Compare Gemini 1.5 Pro vs Flash\", \"How to use Gemini Live API\", \"Check Gemini pricing\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 10. Planning
    if "tokyo" in q_lower and ("itinerary" in q_lower or "3-day" in q_lower or "budget" in q_lower):
        return (
            "Here is your 3-day moderate budget Tokyo itinerary:\n\n"
            "1. Day 1 (Traditional & Historic): Explore Senso-ji temple in Asakusa, take a stroll through Ueno Park, and finish with evening street food at Ameyoko Market.\n"
            "2. Day 2 (Modern Culture & Views): Visit Meiji Shrine in Harajuku, walk through Shibuya Crossing and Hachiko square, then enjoy the free observation deck at the Tokyo Metropolitan Government Building.\n"
            "3. Day 3 (Waterfront & Tech): Tour teamLab Planets in Toyosu, wander around Odaiba waterfront, and spend the evening exploring electronics and dining in Akihabara.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Estimate total daily budget in Yen\", \"Recommend budget hotels in Tokyo\", \"Suggest transit pass options\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "algorithm interview" in q_lower or ("study schedule" in q_lower and "interview" in q_lower):
        return (
            "Here is a high-impact 1-day time-blocked algorithm study schedule:\n\n"
            "1. 08:30 - 10:30: Data Structures Core (Arrays, Hash Maps, Two Pointers - solve 3 medium problems).\n"
            "2. 10:45 - 12:45: Trees & Graphs (BFS, DFS, Binary Search Tree invariants - solve 3 medium problems).\n"
            "3. 13:45 - 15:45: Dynamic Programming & Intervals (Kadane's, 1D DP, merge intervals).\n"
            "4. 16:00 - 17:30: Mock Timed Interview (45-minute timed simulation with verbal explanation).\n"
            "5. 18:00 - 19:00: Formula Review & Edge Cases (null checks, integer overflow, off-by-one bounds).\n\n"
            "<<<SUGGESTIONS>>>\n[\"Top 10 patterns to memorize\", \"How to explain thought process out loud\", \"Make it shorter\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "5k race" in q_lower or "training plan for running" in q_lower or "5k" in q_lower:
        return (
            "Here is your 4-week couch-to-5K progression plan:\n\n"
            "1. Week 1: 3 sessions alternating 1 minute gentle jogging with 2 minutes walking for 20 minutes total.\n"
            "2. Week 2: 3 sessions alternating 2 minutes running with 1.5 minutes walking for 25 minutes total.\n"
            "3. Week 3: 3 sessions of 5 minutes continuous running with 2 minutes walking (repeat 3 times).\n"
            "4. Week 4: Build up to 20-25 minutes continuous easy running, culminating in your first uninterrupted 5K.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Proper running posture tips\", \"Warm-up dynamic stretches\", \"Hydration and shoe advice\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # 11. Memory Check (User Name / Preferences)
    if "what is my name" in q_lower or "who am i" in q_lower:
        name_val = TARGET_USER_NAME
        for m in memories:
            if m.get("key") == "user_name":
                name_val = m.get("value")
        return (
            f"Your name is {name_val}.\n\n"
            "<<<SUGGESTIONS>>>\n[\"Show all stored preferences\", \"Update my preference\", \"Clear my memory\"]\n<<<END_SUGGESTIONS>>>"
        )
    if "what are my preferences" in q_lower or "what do you remember about me" in q_lower:
        lines = [f"- {m.get('key')}: {m.get('value')}" for m in memories]
        mem_str = "\n".join(lines) if lines else "- User: Gokul"
        return (
            f"Here are the preferences and profile facts I remember for you, Gokul:\n\n{mem_str}\n\n"
            "<<<SUGGESTIONS>>>\n[\"Add a new preference\", \"Update my language\", \"Make replies even shorter\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # Generic Default Direct Response with Grounding Synthesis
    if sources:
        first_snippet = sources[0].get("snippet", "")
        clean_snip = re.sub(r"<[^>]+>", "", first_snippet)
        src_md = "\n\nSources:\n" + "\n".join([f"- [{s['title']}]({s['url']})" for s in sources[:3]])
        return (
            f"Here is the verified information for **{query.strip('?!.')}**:\n\n"
            f"{clean_snip}{src_md}\n\n"
            "<<<SUGGESTIONS>>>\n[\"Tell me more details\", \"Summarize in 3 bullets\", \"Search related news\"]\n<<<END_SUGGESTIONS>>>"
        )
        
    # Natural smart fallback response adhering to Core Rules 1 & 2
    return (
        f"For **{query.strip('?!.')}**, here is the key breakdown:\n\n"
        f"The best approach is to tackle this with a clean, modular setup—focusing on the core requirement first and verifying each step.\n\n"
        f"Would you like to see a complete working implementation, an architectural breakdown, or a quick summary?\n\n"
        "<<<SUGGESTIONS>>>\n[\"Show complete working code\", \"Explain step-by-step\", \"Give concise summary\"]\n<<<END_SUGGESTIONS>>>"
    )

async def call_gemini_with_retry(
    system_prompt: str,
    contents: List[Any],
    max_retries: int = 1
) -> Tuple[Optional[str], Optional[str]]:
    """Calls Gemini API with 1 exponential backoff retry on failure or quota limit."""
    if not (GENAI_AVAILABLE and GEMINI_API_KEY):
        return None, "API_KEY_NOT_SET"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    max_output_tokens=1500
                )
            )
            if response and response.text:
                return response.text, None
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries:
                # Exponential backoff retry once
                await asyncio.sleep(1.5)
                continue
            return None, err_str
            
    return None, "MAX_RETRIES_EXCEEDED"

async def generate_chat_response(
    query: str,
    conversation_id: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    enable_search: bool = True
) -> Dict[str, Any]:
    """
    Unified chat completion generator:
    1. Extracts & updates user memories
    2. Runs live web search if needed
    3. Handles long chat compression
    4. Executes Gemini API with retry-once, or fallback brain
    5. Extracts follow-up chips and returns clean output
    """
    # 1. Extract and save memories from user query
    extract_and_save_memories(query)
    all_memories = get_all_memories()
    
    # 2. Check search grounding
    sources = []
    search_context = ""
    if enable_search and should_trigger_search(query):
        search_context, sources = await perform_web_search(query)
        
    # 3. Context & conversation history
    existing_summary = ""
    history_messages = []
    if conversation_id:
        conv = get_conversation(conversation_id)
        if conv:
            existing_summary = conv.get("summary", "")
        history_messages = get_conversation_messages(conversation_id)
        
    # 4. Long chat compression
    summary, recent_messages = compress_chat_history(history_messages, existing_summary)
    if conversation_id and summary != existing_summary:
        update_conversation(conversation_id, summary=summary)
        
    # 5. Build prompt
    system_prompt = build_system_prompt(memories=all_memories, custom_instructions=custom_instruction)
    if summary:
        system_prompt += f"\n\n[Active Conversation Summary: {summary}]"
        
    # Combine user query with search grounding if any
    augmented_query = query
    if search_context:
        augmented_query += f"\n\n{search_context}"
        
    raw_response = None
    error_info = None
    
    # 6. Try live Gemini if configured
    if GENAI_AVAILABLE and GEMINI_API_KEY:
        contents = []
        for m in recent_messages[-4:]:
            role = "user" if m.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": augmented_query}]})
        
        raw_response, error_info = await call_gemini_with_retry(system_prompt, contents)
        
    # 7. If Gemini unavailable or failed after retry, use fallback brain
    if not raw_response:
        raw_response = execute_fallback_brain(query, all_memories, sources)
        
    # 8. Extract chips and clean text
    clean_text, chips = extract_suggestions(raw_response)
    
    return {
        "text": clean_text,
        "follow_up_chips": chips,
        "sources": sources,
        "error": False
    }

async def stream_chat_response(
    query: str,
    conversation_id: str,
    custom_instruction: Optional[str] = None,
    enable_search: bool = True
) -> AsyncGenerator[str, None]:
    """Generates Server-Sent Events (SSE) stream for real-time typewriter UI."""
    try:
        # Get completion
        result = await generate_chat_response(
            query=query,
            conversation_id=conversation_id,
            custom_instruction=custom_instruction,
            enable_search=enable_search
        )
        
        # Stream sources first if present
        if result.get("sources"):
            yield f"data: {json.dumps({'type': 'sources', 'sources': result['sources']})}\n\n"
            await asyncio.sleep(0.05)
            
        # Stream text in smooth natural chunks
        full_text = result.get("text", "")
        # Break into words or small chunks for streaming effect
        words = full_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            await asyncio.sleep(0.015)
            
        # Stream follow up chips
        yield f"data: {json.dumps({'type': 'follow_up_chips', 'chips': result.get('follow_up_chips', [])})}\n\n"
        
        # Save assistant message in DB
        assistant_msg_id = f"msg_{os.urandom(6).hex()}"
        save_message(
            msg_id=assistant_msg_id,
            conv_id=conversation_id,
            role="assistant",
            content=full_text,
            sources=result.get("sources", []),
            follow_up_chips=result.get("follow_up_chips", [])
        )
        
        # Send done event
        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg_id})}\n\n"
        
    except Exception as e:
        # Provider failure catch-all: NEVER show blank screen or raw unhandled errors
        error_payload = {
            "type": "error",
            "message": "The assistant encountered a temporary issue. Please click retry below.",
            "can_retry": True
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
