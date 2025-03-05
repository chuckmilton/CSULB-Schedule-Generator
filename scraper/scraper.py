import requests
from bs4 import BeautifulSoup
import os

# Define all subject codes in a global list so we can re-use it in /scrape_courses.
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

        for course_block in course_blocks:
            # Extract course code and title from the course block
            course_header = course_block.find('div', class_='courseHeader')
            if course_header:
                course_code = course_header.find('span', class_='courseCode').text.strip()
                course_title = course_header.find('span', class_='courseTitle').text.strip()
                units = course_header.find('span', class_='units').text.strip() if course_header.find('span', 'units') else ''

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
                        if not section_number:
                            continue

                        # Check if "SEM" or "LAB" is present in the CLASS NOTES column
                        if "SEM" in class_notes:
                            course_type = "SEMINAR"
                        elif "LAB" in class_notes:
                            course_type = "LAB"
                        elif "LEC" in class_notes:
                            course_type = "LECTURE"
                        elif "ACT" in class_notes:
                            course_type = "ACTIVITY"
                        elif "SUP" in class_notes:
                            course_type = "SUPPLEMENTAL"
                        else:
                            course_type = ""

                        # Extract other information
                        days = columns[5].text.strip()
                        day = " ".join([
                            "Monday" if "M" in days else "",
                            "Tuesday" if "Tu" in days else "",
                            "Wednesday" if "W" in days else "",
                            "Thursday" if "Th" in days else "",
                            "Friday" if "F" in days else "",
                            "Saturday" if "Sa" in days else "",
                            "Sunday" if "Su" in days else "",
                        ]).strip()

                        # Update the code that processes time data
                        time = columns[6].text.strip()  # Extract time
                        time_parts = time.split('-')

                        if len(time_parts) == 2:
                            start_time, end_time = time_parts[0].strip(), time_parts[1].strip()

                            # Process and format the start time
                            start_time_parts = start_time.split(':')
                            if len(start_time_parts) == 1:
                                start_time = f"{start_time}:00"
                            elif len(start_time_parts) == 2:
                                start_time = f"{start_time_parts[0].zfill(2)}:{start_time_parts[1].zfill(2)}"

                            # Process and format the end time
                            end_time_parts = end_time.split(':')
                            if len(end_time_parts) == 1:
                                end_time = f"{end_time}:00"
                            elif len(end_time_parts) == 2:
                                end_time = f"{end_time_parts[0].zfill(2)}:{end_time_parts[1].zfill(2)}"

                            e_time = end_time.replace('AM', '').replace('PM', '')

                            # Adding AM/PM in start_time format based on class time context
                            if "AM" in end_time:
                                start_time += "AM"
                            elif "PM" in end_time:
                                start_hours, _ = map(int, start_time.split(':'))
                                end_hours, _ = map(int, e_time.split(':'))
                                if end_hours == 12 and start_hours < 12:
                                    start_time += "AM"
                                elif start_hours > end_hours:
                                    start_time += "AM" if start_hours != 12 else "PM"
                                elif (end_hours - start_hours) <= 5:
                                    start_time += "PM"

                            # Combine start and end times with a hyphen to represent the range
                            time = f"{start_time}-{end_time}"

                        location = columns[8].text.strip()
                        instructor = columns[9].text.strip()
                        comment = columns[10].text.strip() if len(columns) > 10 else ""

                        green_dot_img = row.find('img', alt='Seats available', title='Seats available')
                        yellow_dot_img = row.find('img', alt='Reserve Capacity', title='Reserve Capacity')
                        seats_available = "Seats Available" if green_dot_img else "Reserve Capacity" if yellow_dot_img else "No Seats Available"

                        if seats_available == "Seats Available":
                            course_data.append(
                                (course_code, course_title, units, section_number, course_type, day, time, location,
                                 instructor, seats_available, comment))

        return course_data
    else:
        return []


def fetch_and_store_courses(semester):
    """
    Collects data from all subject_codes, returns a big list of course tuples.
    This function is now only used if no cache is found.
    """
    all_course_data = []
    for subject_code in subject_codes:
        data = courses(semester, subject_code)
        all_course_data.extend(data)
    return all_course_data


def filter_courses(course_data, selected_courses):
    """
    Filter the course data based on which courses the user selected.
    e.g., if user picks ["CECS", "MATH"], we keep only those course_code prefix.
    """
    return [course for course in course_data if course[0] in selected_courses]
