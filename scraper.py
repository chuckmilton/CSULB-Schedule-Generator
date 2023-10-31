import requests
from bs4 import BeautifulSoup
import sqlite3
import os

text_file = 'course_info.csv'

# Delete the existing database file if it exists
if os.path.exists('courses.db'):
    os.remove('courses.db')


def courses(semester, subject_code):
    # Define the URL of the web page you want to scrape
    url = f'http://web.csulb.edu/depts/enrollment/registration/class_schedule/{semester}/By_Subject/{subject_code}.html'

    # Send an HTTP GET request to the URL
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the HTML content of the page using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all course blocks
        course_blocks = soup.find_all('div', class_='courseBlock')

        course_data = []

        # Open the text file for writing
        with open(text_file, 'w', encoding='utf-8') as file:
            # Write the header to the text file
            file.write("Course Code\tCourse Title\tUnits\tClass #\tType\t"
                       "Days\tTime\tLocation\tInstructor\tSeats Available\tComment\n")

            for course_block in course_blocks:
                # Extract course code and title from the course block
                course_header = course_block.find('div', class_='courseHeader')
                if course_header:
                    course_code = course_header.find('span', class_='courseCode').text.strip()
                    course_title = course_header.find('span', class_='courseTitle').text.strip()

                    units = course_header.find('span', class_='units').text.strip() if course_header.find('span',
                                                                                                          class_='units') else ''

                # Find the table containing section information
                group_sections = course_block.find_all('table', class_='sectionTable')
                if course_code and course_title and group_sections:
                    # Iterate over each row in the table (excluding the header row)
                    for group_section in group_sections:
                        for row in group_section.find_all('tr')[1:]:
                            # Extract data from each column in the row
                            columns = row.find_all('td')
                            section_number = columns[0].text.strip()  # Extract section number
                            class_notes = columns[4].text.strip()  # Extract CLASS NOTES

                            # Check if "SEM" or "LAB" is present in the CLASS NOTES column
                            if "SEM" in class_notes:
                                course_type = "SEMINAR"
                            elif "LAB" in class_notes:
                                course_type = "LAB"
                            elif "LEC" in class_notes:
                                course_type = "LECTURE"
                            elif "ACT" in class_notes:
                                course_type = "ACTIVITY"
                            else:
                                course_type = ""

                            # Extract other information
                            days = columns[5].text.strip()
                            day = ""
                            if "M" in days:
                                day = day + "Monday "
                            if "Tu" in days:
                                day = day + "Tuesday "
                            if "W" in days:
                                day = day + "Wednesday "
                            if "Th" in days:
                                day = day + "Thursday "
                            if "F" in days:
                                day = day + "Friday "
                            if "Sa" in days:
                                day = day + "Saturday "

                            # Update the code that processes time data
                            time = columns[6].text.strip()  # Extract time
                            time_parts = time.split('-')

                            if len(time_parts) == 2:
                                start_time, end_time = time_parts[0].strip(), time_parts[1].strip()

                                # Process and format the start time
                                start_time_parts = start_time.split(':')
                                if len(start_time_parts) == 1:
                                    if start_time != "10" and start_time != "11" and start_time != "12":
                                        start_time = f"0{start_time}:00"
                                    else:
                                        start_time = f"{start_time}:00"
                                elif len(start_time_parts) == 2:
                                    if len(start_time_parts[0]) == 1:
                                        start_time = f"0{start_time}"
                                    if len(start_time_parts[1]) == 1:
                                        start_time = f"{start_time_parts[0]}:0{start_time_parts[1]}"

                                # Process and format the end time
                                end_time_parts = end_time.split(':')
                                if len(end_time_parts) == 1:
                                    if end_time != "10" and end_time != "11":
                                        end_time = f"0{end_time}:00"
                                    else:
                                        end_time = f"{end_time}:00"
                                elif len(end_time_parts) == 2:
                                    if len(end_time_parts[0]) == 1:
                                        end_time = f"0{end_time}"
                                    if len(end_time_parts[1]) == 1:
                                        end_time = f"{end_time_parts[0]}:0{end_time_parts[1]}"

                                e_time = end_time.replace('AM', '').replace('PM', '')

                                # Adding AM/PM in start_time format based on context of schedule of classes
                                # We assume that there are no extreme cases such as classes greater than 12 hours
                                if "AM" in end_time:
                                    start_time += "AM"
                                elif "PM" in end_time:
                                    start_hours, start_minutes = map(int, start_time.split(':'))
                                    end_hours, end_minutes = map(int, e_time.split(':'))

                                    if end_hours == 12 and start_hours < 12:
                                        start_time += "AM"
                                    elif start_hours > end_hours:
                                        if start_hours == 12:
                                            start_time += "PM"
                                        else:
                                            start_time += "AM"
                                    elif (end_hours - start_hours) <= 5:
                                        start_time += "PM"

                                # Combine start and end times with a hyphen to represent the range
                                time = f"{start_time}-{end_time}"

                            location = columns[8].text.strip()
                            instructor = columns[9].text.strip()
                            comment = columns[10].text.strip() if len(columns) > 10 else ""

                            green_dot_img = row.find('img', alt='Seats available', title='Seats available')
                            yellow_dot_img = row.find('img', alt='Reserve Capacity', title='Reserve Capacity')
                            seats_available = ''
                            if green_dot_img:
                                seats_available = "Seats Available"
                            elif yellow_dot_img:
                                seats_available = "Reserve Capacity"
                            else:
                                seats_available = "No Seats Available"

                            # Now you can use the "seats_available" variable as needed, e.g., print it

                            # Write the data to the text file with tab-separated values
                            file.write(
                                f"Course Code: {course_code}\tCourse Title: {course_title}\tUnits: {units}\tClass #: {section_number}\t"
                                f"Course Type: {course_type}\t Days Available: {day}\t Times available: {time}\t"
                                f"Location: {location}\t Professor: {instructor}\t Seats Available: {seats_available} "
                                f"Additional Info: {comment}\n\n")

                            course_data.append(
                                (course_code, course_title, units, section_number, course_type, day, time, location,
                                 instructor, seats_available, comment))

        #print(f"Course information has been saved to {text_file}.")
        return course_data
    else:
        #print(f"Failed to retrieve the web page. Status code: {response.status_code}")
        return []


def save_to_database(data):
    conn = sqlite3.connect('courses.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS courses (
    course_code TEXT,
    course_title TEXT,
    units TEXT,
    section_number TEXT,
    course_type TEXT,
    days TEXT,
    times TEXT,
    location TEXT,
    instructor TEXT,
    seats_available TEXT,
    comment TEXT
    )''')

    for course_data in data:
        cursor.execute(
            'INSERT INTO courses (course_code, course_title, units, section_number, course_type, days, '
            'times, location, instructor, seats_available, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            course_data)

    conn.commit()
    conn.close()


def fetch_and_store_courses(semester):
    all_course_data = []

    # Add all subject codes you want to scrape here
    subject_codes = ['ACCT', 'AFRS', 'ASLD', 'AIS', 'AMST', 'ANTH', "ARAB", "ART", "AH", "AAAS", "ASAM", "AxST", "ASTR",
                     "AT", "BIOL", "BME", "BLAW", "CBA", "KHMR", "CHzE", "CHEM", "CHLS", "CDFS", "CHIN", "CzE", "CLSC",
                     "COMM", "CWL", "CECS", "XYZ", "CEM", "CAFF", "COUN", "CRJU", "XENR", "DANC", "DESN", "DPT", "ERTH",
                     "ECON", "EDLD", "EDCI", "EDEC", "EDEL", "EDSE", "EDSS", "EDSP", "EDAD", "EDzP", "ETEC", "EzE",
                     "EMER", "ENGR", "EzT", "ENGL", "ES", "ENV", "ESzP", "EESJ", "FMD", "FIL", "FEA", "FIN", "FSCI",
                     "FREN", "GEOG", "GERM", "GERN", "GBA", "GK", "HCA", "HzSC", "HEBW", "HIND", "HIST", "HM", "HDEV",
                     "HRM", "IzS", "INTL", "IxST", "ITAL", "JAPN", "JOUR", "KIN", "KOR", "LAT", "CxLA", "LxST", "LING",
                     "MGMT", "MKTG", "MATH", "MTED", "MAE", "MzS", "MUS", "NSCI", "NRSG", "NUTR", "OSI", "PHIL", "PHSC",
                     "PHYS", "POSC", "PSY", "PPA", "REC", "RxST", "RGR", "RUSS", "SCED", "SzW", "SOC", "SPAN", "SLP",
                     "STAT", "SDHE", "SRL", "SxI", "SCM", "THEA", "TRST", "UNIV", "UHP", "UDCP", "VIET", "WGSS"]

    for subject_code in subject_codes:
        course_data = courses(semester, subject_code)
        all_course_data.extend(course_data)

    # Store all_course_data in the SQLite database
    save_to_database(all_course_data)
    return all_course_data


def filter_courses(course_data, selected_courses):
    # Filter the course data based on selected courses
    filtered_courses = [course for course in course_data if course[0] in selected_courses]
    return filtered_courses
