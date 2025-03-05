# CSULB Course Schedule Generator

## Overview
The **CSULB Course Schedule Generator** is a Flask-based web application that helps students generate optimized course schedules based on their selected classes. The system fetches real-time course data from CSULB’s website using web scraping, stores the data in **Supabase**, and allows users to generate schedule combinations while applying filters such as professor exclusions, time constraints, and specific day preferences.

### Hosting & Infrastructure
- **Frontend & Backend**: Flask (Hosted on **Vercel**)
- **Database**: Supabase (PostgreSQL)
- **Web Scraping & Data Updates**: AWS Lambda (Scheduled)

---
## Features
- **Real-Time Course Data**: Scrapes CSULB’s course schedule every few hours.
- **Schedule Generation**: Optimizes schedules based on user preferences.
- **Filters**:
  - Exclude certain professors
  - Exclude time slots or specific days
  - Custom time constraints
- **Responsive UI**: Mobile-friendly design using Tailwind CSS.
- **Calendar Display**: Weekly view for in-person courses.

---
## Installation & Setup
### Prerequisites
Ensure you have the following installed:
- Python 3.x
- Pip
- Virtual environment (optional, but recommended)

### Clone Repository
```bash
git clone https://github.com/chuckmilton/CSULB-Schedule-Generator.git
cd CSULB-Schedule-Generator
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file and add your Supabase credentials:
```ini
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SECRET_KEY=your_flask_secret_key
```

### Running Locally
```bash
python index.py
```

Visit `http://127.0.0.1:5000/` in your browser.

---
## Deployment
### Vercel (Frontend & Backend API)
The Flask application is deployed to **Vercel** for easy access.

1. Install Vercel CLI:
   ```bash
   npm install -g vercel
   ```
2. Deploy:
   ```bash
   vercel
   ```

### AWS Lambda (Scheduled Web Scraping)
To keep course data updated, we run a scheduled job using AWS Lambda:
1. Package the `scheduled_update.py` as a Lambda function.
2. Set up a **CloudWatch** scheduled trigger (e.g., every 24 hours).
