
import sys
import subprocess
import importlib
import requests
import json
from pathlib import Path

def test_python_version():
    """Test Python version compatibility"""
    print("Testing Python version...")
    version = sys.version_info
    if version >= (3, 8):
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} is supported")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} is too old. Requires 3.8+")
        return False

def test_dependencies():
    """Test if all required packages are installed"""
    print("\nTesting Python dependencies...")

    required_packages = [
        'requests', 'beautifulsoup4', 'selenium', 'pandas', 
        'openpyxl', 'ollama', 'webdriver_manager'
    ]

    missing_packages = []

    for package in required_packages:
        try:
            if package == 'beautifulsoup4':
                importlib.import_module('bs4')
            elif package == 'webdriver_manager':
                importlib.import_module('webdriver_manager')
            else:
                importlib.import_module(package.replace('-', '_'))
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - Not installed")
            missing_packages.append(package)

    if missing_packages:
        print(f"\nTo install missing packages, run:")
        print(f"pip install {' '.join(missing_packages)}")
        return False

    return True

def test_chrome_installation():
    """Test if Chrome is installed"""
    print("\nTesting Chrome installation...")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # This will download ChromeDriver if needed
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get("https://www.google.com")
        driver.quit()

        print("✓ Chrome and ChromeDriver are working")
        return True

    except Exception as e:
        print(f"✗ Chrome/ChromeDriver issue: {e}")
        print("  Make sure Google Chrome is installed and updated")
        return False

def test_ollama_connection():
    """Test Ollama installation and connection"""
    print("\nTesting Ollama connection...")

    try:
        import ollama

        # Test if Ollama service is running
        models = ollama.list()
        print("✓ Ollama service is running")

        # Check for required model
        model_names = [model['name'] for model in models['models']]
        if any('llama3' in name for name in model_names):
            print("✓ llama3 model is available")
        else:
            print("⚠ llama3 model not found")
            print("  Run: ollama pull llama3")
            return False

        # Test a simple chat
        response = ollama.chat(
            model='llama3',
            messages=[{'role': 'user', 'content': 'Say hello'}]
        )
        print("✓ Ollama chat is working")
        return True

    except Exception as e:
        print(f"✗ Ollama connection failed: {e}")
        print("  1. Install Ollama from https://ollama.ai/")
        print("  2. Run: ollama pull llama3")
        print("  3. Ensure Ollama service is running")
        return False

def test_file_structure():
    """Test if all required files are present"""
    print("\nTesting file structure...")

    required_files = [
        'job_scraper_enhanced.py',
        'config.json',
        'company_urls.txt',
        'requirements.txt'
    ]

    all_present = True

    for file in required_files:
        if Path(file).exists():
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - Missing")
            all_present = False

    return all_present

def test_internet_connection():
    """Test internet connectivity"""
    print("\nTesting internet connection...")

    try:
        response = requests.get('https://www.google.com', timeout=10)
        if response.status_code == 200:
            print("✓ Internet connection is working")
            return True
        else:
            print(f"✗ Internet connection issue: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Internet connection failed: {e}")
        return False

def test_sample_scrape():
    """Test a simple scraping operation"""
    print("\nTesting sample web scraping...")

    try:
        import requests
        from bs4 import BeautifulSoup

        # Test scraping a simple, reliable site
        url = "https://httpbin.org/html"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text()

        if len(text) > 0:
            print("✓ Basic web scraping is working")
            return True
        else:
            print("✗ Web scraping returned no content")
            return False

    except Exception as e:
        print(f"✗ Web scraping test failed: {e}")
        return False

def run_all_tests():
    """Run all tests and provide summary"""
    print("="*50)
    print("JOB SCRAPER SETUP VERIFICATION")
    print("="*50)

    tests = [
        ("Python Version", test_python_version),
        ("Dependencies", test_dependencies),
        ("Chrome Browser", test_chrome_installation),
        ("Ollama Service", test_ollama_connection),
        ("File Structure", test_file_structure),
        ("Internet Connection", test_internet_connection),
        ("Web Scraping", test_sample_scrape)
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"✗ {test_name} test crashed: {e}")
            results[test_name] = False

    # Summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"{test_name:.<30} {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Your setup is ready to run.")
        print("\nNext steps:")
        print("1. Edit company_urls.txt with your target URLs")
        print("2. Run: python job_scraper_enhanced.py")
        print("3. Set up Task Scheduler for automation")
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Please fix the issues above before running the scraper.")

    return passed == total

if __name__ == "__main__":
    run_all_tests()
    input("\nPress Enter to exit...")
