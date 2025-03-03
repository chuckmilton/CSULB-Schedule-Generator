import itertools
import utils.time_test as time_test

def provide_combinations():
    courses = {}
    with open('course_schedule.txt', 'r') as file:
        current_course = {}
        for line in file:
            line = line.strip()
            if line:
                if line.startswith("Course: "):
                    if current_course:
                        course_name = current_course.get("Course", "Unknown Course")
                        course_units = current_course.get("Units", "Unknown Units")
                        course_section = (
                            current_course.get('Days', 'Unknown Days'),
                            current_course.get('Times', 'Unknown Times'),
                            current_course.get('Location', 'Unknown Location'),
                            current_course.get('Professor', 'Unknown Professor')
                        )
                        courses.setdefault((course_name, course_units), []).append(course_section)
                    current_course = {"Course": line.split(": ", 1)[1]}
                else:
                    parts = line.split(": ", 1)
                    if len(parts) == 2:
                        key, value = parts
                        current_course[key] = value

    # Generate all possible combinations of one section per course.
    combinations = list(itertools.product(*courses.values()))
    combo_number = 1

    for combination in combinations:
        schedule = []
        testtime = []
        for idx, ((course_name, course_units), section) in enumerate(zip(courses.keys(), combination), start=1):
            testtime.append(f"Days: {section[0]}")
            testtime.append(f"Times: {section[1]}")
            schedule.append(f"{idx}. {course_name}, Days: {section[0]}, Times: {section[1]}, Location: {section[2]}, Professor: {section[3]}")

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

        if conflict_count == 0:
            print(f'Combination {combo_number}:')
            for entry in schedule:
                print(entry)
            print()
            combo_number += 1
