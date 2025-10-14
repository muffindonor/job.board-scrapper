# Create comprehensive requirements.txt for V4
requirements_v4 = """# Job Scraper V4 - Python Dependencies

# Web Scraping
requests>=2.31.0
beautifulsoup4>=4.12.2
lxml>=4.9.3

# Browser Automation
selenium>=4.15.0
webdriver-manager>=4.0.1

# Google Sheets Integration
gspread>=5.12.0
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1

# Data Processing
pandas>=2.1.0
openpyxl>=3.1.2

# LLM Integration
ollama>=0.1.7

# Utilities
python-dateutil>=2.8.2
"""

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(requirements_v4.strip())

print("✅ Created requirements.txt")
print()
print("📦 DEPENDENCIES INCLUDED:")
print()
print("🌐 Web Scraping:")
print("  • requests - HTTP library")
print("  • beautifulsoup4 - HTML parsing")
print("  • lxml - XML/HTML parser")
print()
print("🤖 Browser Automation:")
print("  • selenium - Browser control")
print("  • webdriver-manager - Auto Chrome driver management")
print()
print("📊 Google Sheets:")
print("  • gspread - Google Sheets API")
print("  • google-auth - Authentication")
print("  • google-auth-oauthlib - OAuth support")
print("  • google-auth-httplib2 - HTTP transport")
print()
print("📈 Data Processing:")
print("  • pandas - Data manipulation")
print("  • openpyxl - Excel file support")
print()
print("🤖 LLM Integration:")
print("  • ollama - Ollama API client")
print()
print("🔧 Utilities:")
print("  • python-dateutil - Date parsing")
print()
print("💻 INSTALLATION:")
print("  pip install -r requirements.txt")
print()
print("📝 NOTE:")
print("  • All versions are minimum requirements")
print("  • Compatible with Python 3.8+")
print("  • Tested on Windows 10/11")