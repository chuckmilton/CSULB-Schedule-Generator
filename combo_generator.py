import itertools
import time_test


def provide_combinations():

    courses = {}
    # Open the text file
    with open('course_schedule.txt', 'r') as file:
        current_course = {}  # Initialize a current_course dictionary
        for line in file:
            line = line.strip()
            if line:
                if line.startswith("Course: "):
                    # If we encounter a new course, save the current course (if any) to the courses dictionary
                    if current_course:
                        course_name = current_course.get("Course", "Unknown Course")
                        course_units = current_course.get("Units", "Unknown Units")
                        # Combine course sections under the same course name and units
                        course_section = (
                            current_course.get('Days', 'Unknown Days'),
                            current_course.get('Times', 'Unknown Times'),
                            current_course.get('Location', 'Unknown Location'),
                            current_course.get('Professor', 'Unknown Professor')
                        )
                        courses.setdefault((course_name, course_units), []).append(course_section)
                    # Initialize a new current course
                    course_info = line.split(": ")
                    current_course = {"Course": course_info[1]}
                else:
                    key_value = line.split(": ")
                    if len(key_value) == 2:
                        key, value = key_value
                        current_course[key] = value

    # Generate combinations of courses
    combinations = list(itertools.product(*courses.values()))

    o = 1
    testtime = []
    schedule = []
    # Print the combinations
    for i, combination in enumerate(combinations, start=1):
        for j, ((course_name, course_units), section) in enumerate(zip(courses.keys(), combination), start=1):
            testtime.append(f"Days: {section[0]}")
            testtime.append(f"Times: {section[1]}")
        #check times

            schedule.append(f"{j}. {course_name}, Days: {section[0]}, Times: {section[1]}, Location: {section[2]}, Professor: {section[3]}")

        course_count = len(testtime) // 2
        conflict_count = 0

        for k in range(course_count):
            days1 = testtime[k * 2]
            times1 = testtime[k * 2 + 1]

            for p in range(k + 1, course_count):
                days2 = testtime[p * 2]
                times2 = testtime[p * 2 + 1]

                if time_test.are_time_windows_in_conflict(days1, times1, days2, times2):
                    conflict_count += 1

        #print(f'Conflicts: {conflict_count}')
        if conflict_count == 0:
            print(f'Combination {o}:')
            for course in schedule:
                print(course)
            schedule = []
            print()
            o += 1
        else:
            schedule = []
        testtime = []
