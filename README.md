# CSULB Course Schedule Generator

## Overview
The **CSULB Course Schedule Generator** is a Flask-based web application that helps students generate optimized course schedules based on their selected classes. The system fetches real-time course data from CSULB’s website using web scraping, stores the data in **Supabase**, and allows users to generate schedule combinations while applying filters such as professor exclusions, time constraints, and specific day preferences.

### Hosting & Infrastructure
- **Frontend & Backend**: Flask (Hosted on **Vercel**)
- **Database**: Supabase (PostgreSQL)
- **Web Scraping & Data Updates**: AWS Lambda (Scheduled)

---
## 🔥 New Features & Enhancements
### ✅ **Advanced Caching**
- Implements caching with **Redis** for storing schedule combinations and RateMyProfessors (RMP) API responses.  
- Falls back to an in-memory cache if Redis is unavailable, ensuring uninterrupted performance.  
- Redis cache automatically refreshes every 24 hours.  

### ⭐ **RateMyProfessors Integration**
- Integrates with RateMyProfessors using a GraphQL API to fetch professor ratings and profile links.  
- Cleans and maps professor names using a `nameMappings.json` file for better matching.  
- Caches API responses for 24 hours to reduce redundant requests.  
- Professor ratings are clickable in the calendar view for quick access to detailed reviews.  

### 📅 **Dynamic Schedule Generation**
- Uses **itertools.product** to generate all possible combinations of course sections.  
- Filters out conflicting schedules by checking time overlaps using a custom time comparison utility.  
- Deduplicates schedules by creating unique signatures based on course meeting days and times.  

### 🎨 **Interactive & Responsive Frontend**
- Built with **Tailwind CSS** for a modern, mobile-friendly design.  
- Enhanced form inputs using **Tom Select** for searchable, multi-select dropdowns.  
- Dynamic animations using **Animate.css** for form elements and calendar transitions.  
- Displays generated schedules in an interactive weekly calendar view with color-coded events.  
- Added dynamic hover and click interactions for course blocks in the calendar view.  

### 🔄 **Pagination & Custom WSGI Adapter**
- Implements pagination to efficiently display large numbers of schedule combinations.  
- Includes a custom WSGI adapter for running the application with Python’s built-in HTTP server, simplifying local testing and deployment.  
- Automatically caches paginated results for faster loading.  

---
## 🚀 Features
- **Real-Time Course Data**: Scrapes CSULB’s course schedule at regular intervals.  
- **Schedule Generation**: Optimizes schedules based on user-selected courses and preferences.  
- **Filters**:
  - Exclude specific professors  
  - Exclude time slots or entire days  
  - Apply custom time constraints  
- **Advanced Caching & API Integration**:  
  - Caches schedule combinations and professor ratings to boost performance.  
  - Fetches and displays professor ratings as clickable links.  
- **Responsive UI**: Mobile-friendly design using Tailwind CSS with enhanced interactive elements.  
- **Calendar Display**: Weekly view calendar for in-person courses with color-coded events and dynamic animations.  
- **Deployment Ready**: Supports deployment on Vercel (frontend & backend) and scheduled data updates via AWS Lambda.  

---
## 🌟 Additional Notes
### 🧠 **Custom WSGI Adapter**  
- A custom WSGI adapter is provided to run the Flask app with Python’s built-in HTTP server.  
- This simplifies local testing or running the app in environments without a full WSGI server.  

### 🔥 **Redis Caching**  
- If Redis is not available, the app automatically switches to in-memory caching.  
- Cached data includes professor ratings, generated schedules, and paginated results.  

### 📅 **Schedule Filtering**  
- The system filters out schedules with overlapping time slots.  
- Custom filtering options allow for complex time and professor exclusions.  

### **Disclaimer**
**This website is an independent project and is not affiliated with or endorsed by California State University, Long Beach (CSULB).** The use of CSULB's colors and thematic elements is solely for stylistic purposes.