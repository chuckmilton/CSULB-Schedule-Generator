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

CURRENT_SEMESTER = get_current_semester()  # or set a fixed value for testing

def load_cached_courses(semester, cache_age_limit=6 * 3600):
    cache_file = f"cache_{semester}.json"
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < cache_age_limit:
            with open(cache_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    return None
    return None

def save_courses_to_cache(semester, data):
    cache_file = f"cache_{semester}.json"
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
        # For in-person sections, display the actual time.
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
    """
    Checks if event_time (e.g. "05:30PM-06:45PM") overlaps with exclude_range (e.g. "05:00PM-06:00PM").
    Returns True if they overlap.
    """
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
    """
    Checks if event_time (in "%I:%M%p" format, e.g. "05:30PM-06:45PM") overlaps with a custom time range,
    where custom_start and custom_end are in 24-hour format ("HH:MM").
    """
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
# SSE Endpoint: scrape_courses (for progress bar)
# ------------------------------
@app.route("/scrape_courses", methods=["GET"])
def scrape_courses():
    def generate():
        subject_codes = scraper.subject_codes  # subject_codes defined globally in scraper.py
        total = len(subject_codes)
        all_course_data = []
        for i, subject_code in enumerate(subject_codes, start=1):
            data = scraper.courses(CURRENT_SEMESTER, subject_code)
            all_course_data.extend(data)
            progress = int((i / total) * 100)
            yield f"data: {progress}\n\n"
        save_courses_to_cache(CURRENT_SEMESTER, all_course_data)
        yield "data: done\n\n"
    response = app.response_class(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    return response

# ------------------------------
# Form Template (with AJAX, progress bar, filter inputs, and persistent settings)
# ------------------------------
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
    .progress-container {
      width: 100%;
      background-color: #e5e7eb;
      border-radius: 0.375rem;
      overflow: hidden;
    }
    .progress-bar {
      height: 1rem;
      background-color: #3b82f6;
      width: 0%;
      text-align: center;
      color: white;
      line-height: 1rem;
      font-size: 0.75rem;
    }
    .custom-slot { margin-bottom: 0.5rem; }
    .delete-slot { background-color: #ef4444; color: white; border: none; padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer; }
  </style>
</head>
<body class="bg-gray-100">
  <!-- Progress Bar (only shown when re-scraping is needed) -->
  <div id="progressWrapper" class="fixed inset-0 flex flex-col items-center justify-center bg-gray-800 bg-opacity-50 hidden">
    <div class="w-1/2">
      <div id="progressContainer" class="progress-container">
        <div id="progressBar" class="progress-bar">0%</div>
      </div>
      <div class="mt-2 text-white">Retrieving class data...</div>
    </div>
  </div>
  <div class="max-w-xl mx-auto p-6 mt-10 bg-white rounded-lg shadow-lg">
    <p class="text-center mb-4">Semester: <span class="font-semibold">{{ semester.replace('_', ' ') }}</span></p>
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
      <!-- Custom Filter: Multiple Custom Day & Time Slots -->
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
    <p class="text-center text-xs text-gray-400 mt-4">Course data updates per usage.</p>
  </div>
  
  <script>
    let ts1 = new TomSelect("#courses", { maxItems: null, plugins: ['remove_button'] });
    let ts2 = new TomSelect("#exclude_professors", { maxItems: null, plugins: ['remove_button'] });
    let ts3 = new TomSelect("#exclude_times", { maxItems: null, plugins: ['remove_button'] });
    let ts4 = new TomSelect("#exclude_days", { maxItems: null, plugins: ['remove_button'] });
    
    // Function to add another custom slot row with a delete button.
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
    
    // Delegate click event for delete buttons in custom slots.
    document.getElementById("customSlots").addEventListener("click", function(e) {
      if (e.target && e.target.classList.contains("delete-slot")) {
        e.target.parentElement.remove();
      }
    });
    
    // Use the pageshow event to hide the progress bar when returning via back button.
    window.addEventListener("pageshow", function(event) {
      if (performance.getEntriesByType("navigation")[0].type === "back_forward") {
          document.getElementById("progressWrapper").classList.add("hidden");
      }
    });
    
    // On initial DOMContentLoaded, trigger SSE only if the courses select is empty.
    window.addEventListener("DOMContentLoaded", function() {
      let selectElem = document.getElementById("courses");
      if (selectElem.options.length === 0) {
        let evtSource = new EventSource("{{ url_for('scrape_courses') }}");
        document.getElementById("progressWrapper").classList.remove("hidden");
        evtSource.onmessage = function(e) {
          if (e.data === "done") {
            evtSource.close();
            document.getElementById("progressWrapper").classList.add("hidden");
            window.location.reload();
          } else {
            let progress = e.data;
            let progressBar = document.getElementById("progressBar");
            progressBar.style.width = progress + "%";
            progressBar.innerText = progress + "%";
          }
        };
      }
    });
    
    document.getElementById("courseForm").addEventListener("submit", function() {
      document.getElementById("progressWrapper").classList.remove("hidden");
    });
  </script>
</body>
</html>
"""

# ------------------------------
# Results Template (with combination numbering, count, and online section display)
# ------------------------------
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

@app.route("/", methods=["GET"])
def index():
    all_course_data = load_cached_courses(CURRENT_SEMESTER)
    if not all_course_data:
        all_course_data = []
    distinct_courses = sorted({ (course[0], course[1]) for course in all_course_data })
    all_profs = {course[8].strip() for course in all_course_data if course[8].strip()}
    time_ranges = ["08:00AM-09:00AM", "09:00AM-10:00AM", "10:00AM-11:00AM", "11:00AM-12:00PM",
                   "12:00PM-01:00PM", "01:00PM-02:00PM", "02:00PM-03:00PM", "03:00PM-04:00PM",
                   "04:00PM-05:00PM", "05:00PM-06:00PM", "06:00PM-07:00PM"]
    # Retrieve saved settings from session or default to empty lists.
    selected = session.get("selected_courses", [])
    exclude_professors = session.get("exclude_professors", [])
    exclude_times = session.get("exclude_times", [])
    exclude_days = session.get("exclude_days", [])
    exclude_custom = session.get("exclude_custom", [])
    return render_template_string(form_template, semester=CURRENT_SEMESTER, courses=distinct_courses,
                                  selected_courses=selected, professors=sorted(all_profs),
                                  time_ranges=time_ranges, exclude_professors=exclude_professors,
                                  exclude_times=exclude_times, exclude_days=exclude_days, exclude_custom=exclude_custom)

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

    all_course_data = load_cached_courses(CURRENT_SEMESTER)
    if not all_course_data:
        all_course_data = scraper.fetch_and_store_courses(CURRENT_SEMESTER)
        if not all_course_data:
            return "No course data available."
        save_courses_to_cache(CURRENT_SEMESTER, all_course_data)
    
    # Separate online sections and in-person sections.
    online_sections = {}
    inperson_courses_by_code = {}
    for course in all_course_data:
        code = course[0]
        # Use index 6 for the time field and index 10 for the comment field.
        time_field = course[6].strip().lower()  # Normalize for comparison.
        comment_field = course[10].strip().lower()
        if code in selected_courses:
            # If the time field is empty or "na" AND the comment field indicates online class,
            # (we check for "online-no meet times", "no-meet times", or "online no meet times")
            if course[9] == "Seats Available" and (time_field in ["", "na"]) and ("online-no meet times" in comment_field or "no-meet times" in comment_field or "online no meet times" in comment_field):
                # If the section type is empty, assign "Online"
                if not course[4].strip():
                    course[4] = "Online"
                online_sections.setdefault(code, []).append(course)
            # Otherwise, if seats are available and there is a time, treat as in-person.
            elif course[9] == "Seats Available" and time_field not in ["", "na"]:
                inperson_courses_by_code.setdefault(code, {}).setdefault(course[4], []).append(course)
    
    # Do not move online sections to in-person grouping if the course is online-only.
    # (We want to display online classes separately.)
    
    # Check that every selected course has at least one available section.
    for code in selected_courses:
        if code not in inperson_courses_by_code and code not in online_sections:
            return render_template_string(result_template,
                calendars=[f"<div class='text-center text-red-600'>No available sections for {code}.</div>"],
                combination_count=0)
    
    # Build required types for in-person combination generation (only using in-person sections).
    required_types_by_code = {}
    for code in inperson_courses_by_code:
        for sec in sum(inperson_courses_by_code.get(code, {}).values(), []):
            required_types_by_code.setdefault(code, set()).add(sec[4])
    
    # Only generate in-person combinations for courses that have in-person sections.
    courses_for_combinations = {code: secs for code, secs in inperson_courses_by_code.items() if secs}
    
    # If no courses have in-person sections, then display only the online sections.
    if not courses_for_combinations:
        return render_template_string(result_template, calendars=[], combination_count=0, online_sections=online_sections)
    
    # Ensure that for each selected course in in-person grouping, we have at least one section for every required type.
    for code in courses_for_combinations:
        required = required_types_by_code.get(code, set())
        available = set(courses_for_combinations.get(code, {}).keys())
        if not required.issubset(available):
            return render_template_string(result_template,
                calendars=[f"<div class='text-center text-red-600'>No valid in-person sections available for {code} (missing required types).</div>"],
                combination_count=0)
    
    # Generate combinations for in-person sections.
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
                # Skip conflict checking for online sections.
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
    
    # Apply additional filters.
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

handler = app

if __name__ == "__main__":
    app.run(debug=True)

