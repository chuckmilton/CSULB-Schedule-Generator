from flask import Flask, request, render_template_string, redirect, url_for, session, jsonify
import os
import json
import time
from datetime import date, datetime
import itertools
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper import scraper
from utils import time_test
from api.scheduled_update import run_scraper

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

def get_current_semester():
    """
    Determine the current semester based on today's date.
    - If today is on or after October 7, the available semester is Spring of next year.
    - If today is on or after March 10 and before October 7, the available semester is Fall of the current year.
    - Otherwise (before March 10), the available semester is Spring of the current year.
    """
    today = date.today()
    year = today.year
    if today >= date(year, 10, 7):
        return f"Spring_{year + 1}"
    elif today >= date(year, 3, 10):
        return f"Fall_{year}"
    else:
        return f"Spring_{year}"

CURRENT_SEMESTER = get_current_semester()

def load_cached_courses(semester):
    cache_file = os.path.join("/tmp", f"cache_{semester}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data
            except Exception:
                return None
    return None

def save_courses_to_cache(semester, courses):
    cache_file = os.path.join("/tmp", f"cache_{semester}.json")
    data = {
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "courses": courses
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

def format_combination_as_calendar(combination):
    """
    Given a valid schedule combination (a list of course sections),
    return an HTML snippet that renders the schedule as a weekly calendar.
    Each section is added to all days it occurs on.
    """
    week = {
        "Sunday": [],
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": [],
        "Saturday": []
    }
    color_classes = [
        "bg-red-100", "bg-blue-100", "bg-green-100", "bg-yellow-100",
        "bg-purple-100", "bg-pink-100", "bg-indigo-100", "bg-teal-100", "bg-orange-100"
    ]
    color_map = {}
    for sec in combination:
        days_str = sec[5].strip()  # e.g., "Monday Wednesday"
        day_list = days_str.split()
        time_str = sec[6]
        try:
            start_str = time_str.split('-')[0]
            start_time = datetime.strptime(start_str, "%I:%M%p")
        except Exception:
            start_time = None
        if sec[0] not in color_map:
            color_map[sec[0]] = color_classes[len(color_map) % len(color_classes)]
        event = {
            "course": sec[0],
            "section_type": sec[4],
            "units": sec[2],
            "time": sec[6],
            "location": sec[7],
            "professor": sec[8],
            "start": start_time,
            "color": color_map[sec[0]]
        }
        for day in day_list:
            if day in week:
                week[day].append(event)
    for day in week:
        week[day].sort(key=lambda e: e["start"] if e["start"] is not None else datetime.min)
    html = '<div class="grid grid-cols-7 gap-4">'
    for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
        html += f'<div><div class="font-bold text-center border-b pb-2">{day}</div>'
        if week[day]:
            for event in week[day]:
                html += f'<div class="{event["color"]} p-2 rounded mb-2 text-xs">'
                html += f'<div class="font-semibold">{event["course"]} ({event["section_type"]})</div>'
                html += f'<div>{event["time"]}</div>'
                html += f'<div>{event["location"]}</div>'
                html += f'<div>{event["professor"]}</div>'
                html += '</div>'
        else:
            html += '<div class="text-center text-gray-500 text-xs mt-2">—</div>'
        html += '</div>'
    html += '</div>'
    return html

def event_overlaps_exclude_range(event_time, exclude_range):
    try:
        ev_start, ev_end = event_time.split('-')
        ex_start, ex_end = exclude_range.split('-')
        ev_start_dt = datetime.strptime(ev_start.strip(), "%I:%M%p")
        ev_end_dt = datetime.strptime(ev_end.strip(), "%I:%M%p")
        ex_start_dt = datetime.strptime(ex_start.strip(), "%I:%M%p")
        ex_end_dt = datetime.strptime(ex_end.strip(), "%I:%M%p")
        return ev_start_dt < ex_end_dt and ex_start_dt < ev_end_dt
    except Exception:
        return False

def event_overlaps_custom(event_time, custom_start, custom_end):
    try:
        ev_start, ev_end = event_time.split('-')
        ev_start_dt = datetime.strptime(ev_start.strip(), "%I:%M%p")
        ev_end_dt = datetime.strptime(ev_end.strip(), "%I:%M%p")
        cust_start_dt = datetime.strptime(custom_start.strip(), "%H:%M")
        cust_end_dt = datetime.strptime(custom_end.strip(), "%H:%M")
        return ev_start_dt < cust_end_dt and cust_start_dt < ev_end_dt
    except Exception:
        return False

# ------------------------------
# Frontend Templates
# ------------------------------

# Form Template: Loads cached course data (updated externally) and includes a "Refresh Data" button.
form_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Course Schedule Generator</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://cdn.jsdelivr.net/npm/tom-select/dist/css/tom-select.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/tom-select/dist/js/tom-select.complete.min.js"></script>
  <style>
    .custom-slot { margin-bottom: 0.5rem; }
    .delete-slot { background-color: #ef4444; color: white; border: none; padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer; }
  </style>
</head>
<body class="bg-gray-100">
  <div class="max-w-xl mx-auto p-6 mt-10 bg-white rounded-lg shadow-lg">
    <p class="text-center mb-4">Semester: <span class="font-semibold">{{ semester.replace('_', ' ') }}</span></p>
    <!-- Display last updated time if available -->
    {% if last_updated %}
      <p class="text-center text-sm text-gray-600 mb-4">
        Data last updated: {{ last_updated | datetimeformat }}
      </p>
    {% endif %}
    <!-- Refresh Button -->
    <div class="text-center mb-4">
      <a href="{{ url_for('index') }}" class="inline-block bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded">
        Refresh Data
      </a>
    </div>
    <form id="courseForm" action="{{ url_for('generate') }}" method="post">
      <div class="mb-4">
        <label for="courses" class="block text-gray-700 font-medium mb-2">Select Courses:</label>
        <select id="courses" name="courses" multiple class="w-full p-2 border border-gray-300 rounded">
          {% for code, title in courses %}
            <option value="{{ code }}" {% if code in selected_courses %}selected{% endif %}>
              {{ code }} - {{ title }}
            </option>
          {% endfor %}
        </select>
        <p class="text-sm text-gray-500 mt-1">Type to search. Use Ctrl (or Command on Mac) to select multiple.</p>
      </div>
      <!-- Predefined Filters -->
      <div class="mb-4">
        <label for="exclude_professors" class="block text-gray-700 font-medium mb-2">Exclude Professors:</label>
        <select id="exclude_professors" name="exclude_professors" multiple class="w-full p-2 border border-gray-300 rounded">
          {% for prof in professors %}
            <option value="{{ prof }}" {% if prof in exclude_professors %}selected{% endif %}>{{ prof }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-4">
        <label for="exclude_times" class="block text-gray-700 font-medium mb-2">Exclude Time Ranges:</label>
        <select id="exclude_times" name="exclude_times" multiple class="w-full p-2 border border-gray-300 rounded">
          {% for time_range in time_ranges %}
            <option value="{{ time_range }}" {% if time_range in exclude_times %}selected{% endif %}>{{ time_range }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-4">
        <label for="exclude_days" class="block text-gray-700 font-medium mb-2">Exclude Days:</label>
        <select id="exclude_days" name="exclude_days" multiple class="w-full p-2 border border-gray-300 rounded">
          {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
            <option value="{{ day }}" {% if day in exclude_days %}selected{% endif %}>{{ day }}</option>
          {% endfor %}
        </select>
      </div>
      <!-- Custom Filters -->
      <div id="customSlots">
        <label class="block text-gray-700 font-medium mb-2">Exclude Specific Day & Time:</label>
        {% if exclude_custom %}
          {% for custom in exclude_custom %}
          <div class="custom-slot flex space-x-2">
            <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-300 rounded">
              {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
                <option value="{{ day }}" {% if day == custom[0] %}selected{% endif %}>{{ day }}</option>
              {% endfor %}
            </select>
            <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-300 rounded" value="{{ custom[1] }}">
            <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-300 rounded" value="{{ custom[2] }}">
            <button type="button" class="delete-slot">Delete</button>
          </div>
          {% endfor %}
        {% else %}
          <div class="custom-slot flex space-x-2">
            <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-300 rounded">
              {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
                <option value="{{ day }}">{{ day }}</option>
              {% endfor %}
            </select>
            <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-300 rounded">
            <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-300 rounded">
            <button type="button" class="delete-slot">Delete</button>
          </div>
        {% endif %}
      </div>
      <div class="mb-4">
        <button type="button" id="addSlot" class="w-full bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 rounded">
          Add Another Slot
        </button>
      </div>
      <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 rounded">
        Generate Schedule
      </button>
    </form>
    <p class="text-center text-xs text-gray-400 mt-4">Course data updates every 3 hours.</p>
  </div>
  
  <script>
    let ts1 = new TomSelect("#courses", { maxItems: null, plugins: ['remove_button'] });
    let ts2 = new TomSelect("#exclude_professors", { maxItems: null, plugins: ['remove_button'] });
    let ts3 = new TomSelect("#exclude_times", { maxItems: null, plugins: ['remove_button'] });
    let ts4 = new TomSelect("#exclude_days", { maxItems: null, plugins: ['remove_button'] });
    
    // Add new custom slot row.
    document.getElementById("addSlot").addEventListener("click", function() {
      let container = document.getElementById("customSlots");
      let newSlot = document.createElement("div");
      newSlot.className = "custom-slot flex space-x-2 mt-2";
      newSlot.innerHTML = `
        <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-300 rounded">
          <option value="Sunday">Sunday</option>
          <option value="Monday">Monday</option>
          <option value="Tuesday">Tuesday</option>
          <option value="Wednesday">Wednesday</option>
          <option value="Thursday">Thursday</option>
          <option value="Friday">Friday</option>
          <option value="Saturday">Saturday</option>
        </select>
        <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-300 rounded">
        <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-300 rounded">
        <button type="button" class="delete-slot">Delete</button>
      `;
      container.appendChild(newSlot);
    });
    
    // Delete a custom slot row.
    document.getElementById("customSlots").addEventListener("click", function(e) {
      if (e.target && e.target.classList.contains("delete-slot")) {
        e.target.parentElement.remove();
      }
    });
  </script>
</body>
</html>
"""

# Results Template (unchanged)
result_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Course Schedule Results</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100">
  <div class="max-w-5xl mx-auto p-6 mt-10 bg-white rounded-lg shadow-lg">
    <h1 class="text-2xl font-bold text-center mb-6">Generated Course Schedules (Weekly Calendar)</h1>
    {% if online_sections %}
      <div class="mb-6 p-4 border border-green-500 rounded bg-green-50">
        <h2 class="text-xl font-semibold text-center">Online Classes</h2>
        <ul>
          {% for code, sections in online_sections.items() %}
            <li class="mt-2">
              <strong>{{ code }}:</strong>
              {% for sec in sections %}
                {{ sec[4] }} - Online ({{ sec[7] }}, {{ sec[8] }})
                {% if not loop.last %}<br>{% endif %}
              {% endfor %}
            </li>
          {% endfor %}
        </ul>
      </div>
    {% endif %}
    {% if calendars %}
      <h2 class="text-xl font-semibold text-center mb-4">Total Valid In-Person Combinations: {{ combination_count }}</h2>
      {% for calendar in calendars %}
        <div class="mb-8">
          <h3 class="text-lg font-semibold mb-2">Combination {{ loop.index }}:</h3>
          {{ calendar | safe }}
        </div>
      {% endfor %}
    {% else %}
      <div class="text-center text-red-600">No valid in-person schedules available for the selected classes.</div>
    {% endif %}
    <div class="mt-6 text-center">
      <a href="{{ url_for('index') }}" class="bg-gray-600 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded">
        Back
      </a>
    </div>
  </div>
</body>
</html>
"""

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if isinstance(value, str):
        return value
    return datetime.utcfromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S UTC")

@app.route("/", methods=["GET"])
def index():
    data = load_cached_courses(CURRENT_SEMESTER)
    if data is None:
        data = {"courses": []}
        last_updated = None
    elif isinstance(data, list):
        # Fallback if data is a list.
        last_updated = None
        data = {"courses": data}
    else:
        last_updated = data.get("last_updated", None)
    courses = data.get("courses", [])
    distinct_courses = sorted({ (course[0], course[1]) for course in courses })
    all_profs = { course[8].strip() for course in courses if course[8].strip() }
    time_ranges = [
        "08:00AM-09:00AM", "09:00AM-10:00AM", "10:00AM-11:00AM", "11:00AM-12:00PM",
        "12:00PM-01:00PM", "01:00PM-02:00PM", "02:00PM-03:00PM", "03:00PM-04:00PM",
        "04:00PM-05:00PM", "05:00PM-06:00PM", "06:00PM-07:00PM"
    ]
    selected = session.get("selected_courses", [])
    exclude_professors = session.get("exclude_professors", [])
    exclude_times = session.get("exclude_times", [])
    exclude_days = session.get("exclude_days", [])
    exclude_custom = session.get("exclude_custom", [])
    return render_template_string(form_template, semester=CURRENT_SEMESTER, courses=distinct_courses,
                                  selected_courses=selected, professors=sorted(all_profs),
                                  time_ranges=time_ranges, exclude_professors=exclude_professors,
                                  exclude_times=exclude_times, exclude_days=exclude_days, 
                                  exclude_custom=exclude_custom, last_updated=last_updated)

@app.route("/generate", methods=["POST"])
def generate():
    selected_courses = request.form.getlist("courses")
    session["selected_courses"] = selected_courses

    exclude_professors = request.form.getlist("exclude_professors")
    session["exclude_professors"] = exclude_professors

    exclude_times = request.form.getlist("exclude_times")
    session["exclude_times"] = exclude_times

    exclude_days = request.form.getlist("exclude_days")
    session["exclude_days"] = exclude_days

    custom_days = request.form.getlist("exclude_custom_day[]")
    custom_starts = request.form.getlist("exclude_custom_start[]")
    custom_ends = request.form.getlist("exclude_custom_end[]")
    exclude_custom = []
    for day, start, end in zip(custom_days, custom_starts, custom_ends):
        if day and start and end:
            exclude_custom.append((day.strip(), start.strip(), end.strip()))
    session["exclude_custom"] = exclude_custom

    data = load_cached_courses(CURRENT_SEMESTER)
    if data is None:
        courses_data = scraper.fetch_and_store_courses(CURRENT_SEMESTER)
        if not courses_data:
            return "No course data available."
        save_courses_to_cache(CURRENT_SEMESTER, courses_data)
        data = {"courses": courses_data}
    else:
        data = data.get("courses", [])
    
    online_sections = {}
    inperson_courses_by_code = {}
    for course in data:
        code = course[0]
        time_field = course[6].strip().lower()
        comment_field = course[10].strip().lower()
        if code in selected_courses:
            if course[9] == "Seats Available" and (time_field in ["", "na"]) and (
                "online-no meet times" in comment_field or 
                "no-meet times" in comment_field or 
                "online no meet times" in comment_field):
                if not course[4].strip():
                    course[4] = "Online"
                online_sections.setdefault(code, []).append(course)
            elif course[9] == "Seats Available" and time_field not in ["", "na"]:
                inperson_courses_by_code.setdefault(code, {}).setdefault(course[4], []).append(course)
    
    for code in selected_courses:
        if code not in inperson_courses_by_code and code not in online_sections:
            return render_template_string(result_template,
                calendars=[f"<div class='text-center text-red-600'>No available sections for {code}.</div>"],
                combination_count=0)
    
    required_types_by_code = {}
    for code in inperson_courses_by_code:
        for sec in sum(inperson_courses_by_code.get(code, {}).values(), []):
            required_types_by_code.setdefault(code, set()).add(sec[4])
    
    courses_for_combinations = { code: secs for code, secs in inperson_courses_by_code.items() if secs }
    
    if not courses_for_combinations:
        return render_template_string(result_template, calendars=[], combination_count=0, online_sections=online_sections)
    
    for code in courses_for_combinations:
        required = required_types_by_code.get(code, set())
        available = set(courses_for_combinations.get(code, {}).keys())
        if not required.issubset(available):
            return render_template_string(result_template,
                calendars=[f"<div class='text-center text-red-600'>No valid in-person sections available for {code} (missing required types).</div>"],
                combination_count=0)
    
    course_combinations = {}
    for code in courses_for_combinations:
        types = sorted(required_types_by_code.get(code, []))
        sections_lists = [courses_for_combinations[code][t] for t in types]
        course_combinations[code] = list(itertools.product(*sections_lists))
    
    overall_combinations = list(itertools.product(*[course_combinations[code] for code in courses_for_combinations]))
    
    valid_combinations = []
    for overall in overall_combinations:
        schedule_sections = []
        for sections_tuple in overall:
            schedule_sections.extend(sections_tuple)
        conflict = False
        n = len(schedule_sections)
        for i in range(n):
            for j in range(i+1, n):
                sec1 = schedule_sections[i]
                sec2 = schedule_sections[j]
                sec1_time = sec1[6].strip().lower()
                sec2_time = sec2[6].strip().lower()
                if ("na" in sec1_time or sec1_time == "" or
                    "na" in sec2_time or sec2_time == ""):
                    continue
                if time_test.are_time_windows_in_conflict(sec1[5], sec1[6], sec2[5], sec2[6]):
                    conflict = True
                    break
            if conflict:
                break
        if not conflict:
            valid_combinations.append(schedule_sections)
    
    filtered_combinations = []
    for comb in valid_combinations:
        skip = False
        for sec in comb:
            prof = sec[8].strip()
            if prof in exclude_professors:
                skip = True
                break
            for ex_time in exclude_times:
                if event_overlaps_exclude_range(sec[6], ex_time):
                    skip = True
                    break
            if skip:
                break
            event_days = sec[5].split()
            if any(day in event_days for day in exclude_days):
                skip = True
                break
            for custom in exclude_custom:
                custom_day, cust_start, cust_end = custom
                if custom_day in sec[5].split() and event_overlaps_custom(sec[6], cust_start, cust_end):
                    skip = True
                    break
            if skip:
                break
        if not skip:
            filtered_combinations.append(comb)
    
    if not filtered_combinations:
        return render_template_string(result_template,
            calendars=["<div class='text-center text-red-600'>No valid schedules available for the selected classes after applying filters.</div>"],
            combination_count=0)
    
    calendars = []
    for comb in filtered_combinations:
        cal_html = format_combination_as_calendar(comb)
        calendars.append(cal_html)
    
    combination_count = len(filtered_combinations)
    return render_template_string(result_template, calendars=calendars, combination_count=combination_count, online_sections=online_sections)

from http.server import BaseHTTPRequestHandler
from io import BytesIO
from urllib.parse import urlparse

class WSGIAdapter(BaseHTTPRequestHandler):
    def do_GET(self):
        self.wsgi_handle()
    def do_POST(self):
        self.wsgi_handle()
    def wsgi_handle(self):
        environ = {}
        environ['REQUEST_METHOD'] = self.command
        parsed_url = urlparse(self.path)
        environ['PATH_INFO'] = parsed_url.path
        environ['QUERY_STRING'] = parsed_url.query
        environ['SERVER_NAME'] = self.server.server_address[0]
        environ['SERVER_PORT'] = str(self.server.server_address[1])
        environ['wsgi.input'] = self.rfile
        environ['wsgi.errors'] = sys.stderr
        environ['wsgi.version'] = (1, 0)
        environ['wsgi.multithread'] = False
        environ['wsgi.multiprocess'] = False
        environ['wsgi.run_once'] = False
        environ['wsgi.url_scheme'] = 'http'
        length = self.headers.get('Content-Length')
        if length:
            environ['CONTENT_LENGTH'] = length
        environ['CONTENT_TYPE'] = self.headers.get('Content-Type', '')
        response_status = None
        response_headers = None
        def start_response(status, headers, exc_info=None):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = headers
            return lambda x: None
        result = app(environ, start_response)
        response_body = b"".join(result)
        self.send_response(int(response_status.split()[0]))
        for header, value in response_headers:
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

handler = WSGIAdapter

@app.route("/api/scheduled_update", methods=["GET"])
def scheduled_update():
    run_scraper()
    return jsonify({"message": "Course data updated successfully"}), 200

if __name__ == "__main__":
    app.run(debug=True)
