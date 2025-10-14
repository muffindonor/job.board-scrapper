# First address the Ollama issue and requirements
print("🚨 OLLAMA CONNECTION ISSUE - YES YOU'RE ABSOLUTELY RIGHT!")
print("=" * 60)
print("The program SHOULD have told you Ollama wasn't running!")
print("Instead it silently failed and wasted 16 minutes.")
print()
print("CURRENT BROKEN BEHAVIOR:")
print("  1. Try to connect to Ollama")
print("  2. Connection fails silently")  
print("  3. Return empty list []")
print("  4. Continue processing other URLs")
print("  5. Result: 0 jobs with NO warning")
print()
print("WHAT SHOULD HAPPEN:")
print("  1. Try to connect to Ollama at startup")
print("  2. If fails: STOP immediately with clear error")
print("  3. Tell user to start Ollama service")
print("  4. Don't waste time scraping without LLM")
print()
print("✅ FIXED: Will add Ollama connection check at startup")

print()
print("📋 NEW SHEET ORGANIZATION REQUIREMENTS:")
print("=" * 50)
print("CURRENT V4 LOGIC:")
print("  • Sheet2: Regular jobs + Junior/Entry (bold)")  
print("  • Sheet3: Student/Intern positions")
print()
print("NEW REQUIREMENTS:")
print("  • Sheet2: Student/Intern positions")
print("  • Sheet3: Junior/Entry positions (bold)")
print("  • Sheet4: Senior positions")
print("  • Default: Regular jobs (where do these go?)")
print()
print("QUESTIONS TO CLARIFY:")
print("  1. Where do regular jobs go? (non-senior, non-entry, non-intern)")
print("     - New Sheet5 for 'Regular'?")
print("     - Still go to Sheet3 with entry jobs?")
print()
print("  2. Senior job detection:")  
print("     - 'Senior Software Engineer' → Sheet4 ✓")
print("     - 'Senior Data Scientist' → Sheet4 ✓")
print("     - 'Software Engineer Senior' → Sheet4? ✓")
print()

# Show current sheet assignments to verify understanding
sheet_logic = """
PROPOSED NEW SHEET LOGIC:

def categorize_job(title):
    if has_senior_in_title(title):
        return "Sheet4"  # Senior positions
    elif is_student_intern_position(title):
        return "Sheet2"  # Student/Intern (SWAPPED)
    elif is_entry_junior_position(title):  
        return "Sheet3"  # Entry/Graduate (SWAPPED)
    else:
        return "Sheet3"  # Default: Regular jobs with entry jobs?
"""

print("🔄 PROPOSED LOGIC:")
print(sheet_logic)
print()
print("Is this correct? And where should regular jobs go?")

# Create the enhanced version with Ollama check and new sheet logic
enhanced_v4_1 = '''
# V4.1 Preview - Key additions:

def startup_ollama_check(self):
    """Check Ollama connection at startup - FAIL FAST if not available"""
    try:
        self.logger.info("🤖 Testing Ollama connection...")
        test_response = ollama.chat(
            model=self.config['ollama_model'],
            messages=[{'role': 'user', 'content': 'test'}]
        )
        self.logger.info("✅ Ollama connection successful")
        return True
    except Exception as e:
        self.logger.error("❌ OLLAMA CONNECTION FAILED!")
        self.logger.error(f"Error: {e}")
        self.logger.error("SOLUTION:")
        self.logger.error("  1. Start Ollama service: ollama serve")
        self.logger.error("  2. Pull model: ollama pull llama3") 
        self.logger.error("  3. Test: ollama run llama3")
        return False

def is_senior_position(self, title: str) -> bool:
    """Check if position is senior level (Sheet4)"""
    title_lower = title.lower()
    return 'senior' in title_lower

def categorize_job(self, title: str) -> str:
    """Categorize job into appropriate sheet"""
    if self.is_senior_position(title):
        return "Sheet4"  # Senior positions
    elif self.is_student_intern_position(title):
        return "Sheet2"  # Student/Intern (SWAPPED)
    elif self.is_entry_junior_position(title):
        return "Sheet3"  # Entry/Graduate (SWAPPED) 
    else:
        return "Sheet3"  # Default: Regular jobs go with entry jobs
'''

print("💻 KEY CHANGES IN V4.1:")
print("=" * 30)
print("1. ❌ FAIL FAST: Ollama check at startup - stops if not running")
print("2. 🔄 SHEET SWAP: Sheet2=Student/Intern, Sheet3=Entry/Junior") 
print("3. ⭐ NEW SHEET4: Senior positions")
print("4. 🐛 REGEX FIX: Word boundaries for intern detection")
print()
print("Should I implement this V4.1 with these changes?")