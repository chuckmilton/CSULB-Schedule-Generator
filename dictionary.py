# Initialize an empty dictionary to store the courses
courses = {}

# Open the text file
with open('course_schedule.txt', 'r') as file:
    current_course = {}
    for line in file:
        line = line.strip()
        if line:
            if line.startswith("Course: "):
                if current_course:
                    # Add the current course section to the corresponding course name
                    course_name = current_course.get("Course", "Unknown Course")
                    course_section = (
                        f"{current_course.get('Days', 'Unknown Days')} {current_course.get('Times', 'Unknown Times')}",
                        current_course.get('Location', 'Unknown Location'),
                        current_course.get('Professor', 'Unknown Professor')
                    )
                    if course_name in courses:
                        courses[course_name].append(course_section)
                    else:
                        courses[course_name] = [course_section]
                current_course = {"Course": line.split(": ")[1]}
            else:
                key_value = line.split(": ")
                if len(key_value) == 2:
                    key, value = key_value
                    current_course[key] = value

# Add the last course section (if any)
if current_course:
    course_name = current_course.get("Course", "Unknown Course")
    course_section = (
        f"{current_course.get('Days', 'Unknown Days')} {current_course.get('Times', 'Unknown Times')}",
        current_course.get('Location', 'Unknown Location'),
        current_course.get('Professor', 'Unknown Professor')
    )
    if course_name in courses:
        courses[course_name].append(course_section)
    else:
        courses[course_name] = [course_section]