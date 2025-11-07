"""
IBPS Job Listings Scraper
Scrapes job listings from IBPS (Institute of Banking Personnel Selection) website
and saves them to a CSV file.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import warnings

# Try to import certifi for better SSL certificate handling
try:
    import certifi
    import ssl
    CERTIFI_AVAILABLE = True
except ImportError:
    CERTIFI_AVAILABLE = False

# Suppress SSL warnings when verify=False
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

def get_page_content(url, headers=None, verify_ssl=True):
    """
    Fetch the content of a web page.
    
    Args:
        url: The URL to fetch
        headers: Optional headers to send with the request
        verify_ssl: Whether to verify SSL certificates (default: True)
    
    Returns:
        BeautifulSoup object or None if request fails
    """
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    # Try with SSL verification first
    try:
        if CERTIFI_AVAILABLE and verify_ssl:
            # Use certifi's certificate bundle
            response = requests.get(url, headers=headers, timeout=10, verify=certifi.where())
        else:
            response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except requests.exceptions.SSLError as ssl_error:
        print(f"SSL verification error: {ssl_error}")
        if verify_ssl:
            print("Retrying without SSL verification...")
            print("Warning: SSL verification is disabled. This is less secure but may be necessary on some systems.")
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except requests.RequestException as e:
                print(f"Error fetching page even without SSL verification: {e}")
                return None
        else:
            print(f"Error fetching page: {ssl_error}")
            return None
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return None

def extract_job_info(job_element, base_url='https://www.ibps.in'):
    """
    Extract job information from a job listing element.
    
    Args:
        job_element: BeautifulSoup element containing job information
        base_url: Base URL for constructing absolute links
    
    Returns:
        Dictionary with job information or None
    """
    try:
        job_data = {}
        
        # Extract job title - try multiple possible selectors
        title_elem = (job_element.find('h4') or 
                     job_element.find('h3') or 
                     job_element.find('h2') or
                     job_element.find('a', class_=re.compile(r'title|heading|name', re.I)) or
                     job_element.find('span', class_=re.compile(r'title|heading|name', re.I)))
        
        if title_elem:
            job_data['Job Title'] = title_elem.get_text(strip=True)
        else:
            # Fallback: get text from first link
            link_elem = job_element.find('a')
            if link_elem:
                job_data['Job Title'] = link_elem.get_text(strip=True)
            else:
                return None
        
        # Extract location - try multiple possible selectors
        location_elem = (job_element.find('span', class_=re.compile(r'location|place|city', re.I)) or
                        job_element.find('div', class_=re.compile(r'location|place|city', re.I)) or
                        job_element.find(text=re.compile(r'Location|City|Place', re.I)))
        
        if location_elem:
            if isinstance(location_elem, str):
                job_data['Location'] = location_elem.strip()
            else:
                job_data['Location'] = location_elem.get_text(strip=True)
        else:
            job_data['Location'] = 'Not specified'
        
        # Extract date - try multiple possible selectors
        date_elem = (job_element.find('span', class_=re.compile(r'date|published|post', re.I)) or
                    job_element.find('div', class_=re.compile(r'date|published|post', re.I)) or
                    job_element.find('time') or
                    job_element.find(text=re.compile(r'\d{2}[/-]\d{2}[/-]\d{2,4}', re.I)))
        
        if date_elem:
            if isinstance(date_elem, str):
                job_data['Post/Publish Date'] = date_elem.strip()
            else:
                job_data['Post/Publish Date'] = date_elem.get_text(strip=True)
                # Also check for datetime attribute
                if date_elem.get('datetime'):
                    job_data['Post/Publish Date'] = date_elem.get('datetime')
        else:
            job_data['Post/Publish Date'] = 'Not specified'
        
        # Extract link
        link_elem = job_element.find('a', href=True)
        if link_elem:
            link = link_elem.get('href', '')
            # Convert relative URL to absolute
            if link.startswith('/'):
                job_data['Link to Detailed Job Page'] = base_url + link
            elif link.startswith('http'):
                job_data['Link to Detailed Job Page'] = link
            else:
                job_data['Link to Detailed Job Page'] = base_url + '/' + link
        else:
            job_data['Link to Detailed Job Page'] = 'Not available'
        
        return job_data
    
    except Exception as e:
        print(f"Error extracting job info: {e}")
        return None

def scrape_ibps_jobs(url='https://www.ibps.in/', output_file='ibps_job_listings.csv', verify_ssl=True):
    """
    Main function to scrape IBPS job listings.
    
    Args:
        url: URL of the IBPS recruitment/career page
        output_file: Name of the output CSV file
        verify_ssl: Whether to verify SSL certificates (default: True)
    """
    print(f"Fetching job listings from {url}...")
    soup = get_page_content(url, verify_ssl=verify_ssl)
    
    if soup is None:
        print("Failed to fetch the page. Please check your internet connection and try again.")
        return
    
    # Try to find job listings container - check multiple possible structures
    job_container = None
    possible_containers = [
        soup.find('div', class_=re.compile(r'recruit|job|vacancy|opening', re.I)),
        soup.find('section', class_=re.compile(r'recruit|job|vacancy|opening', re.I)),
        soup.find('ul', class_=re.compile(r'recruit|job|vacancy|opening', re.I)),
        soup.find('div', id=re.compile(r'recruit|job|vacancy|opening', re.I)),
        soup.find('div', class_='other_recruitments'),
        soup.find('div', class_='recruitment-list'),
    ]
    
    for container in possible_containers:
        if container:
            job_container = container
            break
    
    # If no specific container found, try to find all links that might be job listings
    if job_container is None:
        print("Could not find job listings container. Trying alternative approach...")
        # Look for common patterns: links with job-related text or in specific sections
        job_container = soup
    
    # Find individual job listings
    jobs = []
    
    # Try multiple selectors for job items
    job_selectors = [
        job_container.find_all('div', class_=re.compile(r'recruitment|job|vacancy|opening|listing', re.I)),
        job_container.find_all('li', class_=re.compile(r'recruitment|job|vacancy|opening|listing', re.I)),
        job_container.find_all('article', class_=re.compile(r'recruitment|job|vacancy|opening|listing', re.I)),
        job_container.find_all('div', class_='recruitment'),
        job_container.find_all('div', class_='job-item'),
    ]
    
    job_elements = []
    for selector in job_selectors:
        if selector:
            job_elements = selector
            break
    
    # If still no jobs found, try finding by link patterns
    if not job_elements:
        print("Trying to find job listings by link patterns...")
        # Look for links that contain job-related keywords
        all_links = job_container.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '').lower()
            text = link.get_text(strip=True).lower()
            if any(keyword in href or keyword in text for keyword in ['recruitment', 'job', 'vacancy', 'notification', 'cwe', 'exam']):
                # Get parent element that likely contains job details
                parent = link.find_parent(['div', 'li', 'article', 'tr'])
                if parent and parent not in job_elements:
                    job_elements.append(parent)
    
    print(f"Found {len(job_elements)} potential job listings.")
    
    # Extract information from each job listing
    exclude_keywords = ['view all', 'all', 'recruitment exams', 'personnel selection services']
    
    for job_elem in job_elements:
        job_info = extract_job_info(job_elem)
        if job_info and job_info['Job Title']:
            # Filter out non-job entries
            title_lower = job_info['Job Title'].lower().strip()
            if not any(keyword in title_lower for keyword in exclude_keywords):
                # Also exclude if title is too long (likely not a job title)
                if len(job_info['Job Title']) < 100:
                    jobs.append(job_info)
    
    if not jobs:
        print("\nNo jobs found. This could mean:")
        print("1. The website structure has changed")
        print("2. There are currently no job listings")
        print("3. The page requires JavaScript to load content")
        print("\nPlease inspect the website manually and update the selectors in the script.")
        print("\nYou can save the HTML of the page and check its structure:")
        print("  - Right-click on the page -> Inspect Element")
        print("  - Look for the container holding job listings")
        print("  - Note the class names and HTML structure")
        return
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(jobs)
    
    # Remove duplicates based on job title and link
    df = df.drop_duplicates(subset=['Job Title', 'Link to Detailed Job Page'], keep='first')
    
    # Save to CSV
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"\nSuccessfully scraped {len(df)} job listings!")
    print(f"Results saved to: {output_file}")
    print("\nFirst few listings:")
    print(df.head().to_string(index=False))

if __name__ == "__main__":
    # You can modify these URLs based on the actual IBPS recruitment page
    ibps_urls = [
        'https://www.ibps.in/',
        'https://www.ibps.in/careers/',  # Alternative URL if exists
        'https://www.ibps.in/recruitment/',  # Alternative URL if exists
    ]
    
    # Try the main URL first
    # The script will automatically retry without SSL verification if SSL verification fails
    scrape_ibps_jobs(url=ibps_urls[0], output_file='ibps_job_listings.csv', verify_ssl=True)
    
    # If you need to try alternative URLs, uncomment below:
    # for url in ibps_urls[1:]:
    #     print(f"\nTrying alternative URL: {url}")
    #     scrape_ibps_jobs(url=url, output_file='ibps_job_listings.csv', verify_ssl=True)

