import scraper


def main():
    semester = input('Enter the semester (e.g., Fall_2023, Spring_2024, etc.): ')
    print('Loading courses...\n')
    all_course_data = scraper.fetch_and_store_courses(semester)

    if not all_course_data:
        print("No course data available.")
        return

    selected_courses = input(
        "Enter the courses you want to take (comma-separated, e.g., CECS 100, MATH 123, PHYS 151): ").split(", ")

    # Filter the course data based on selected courses
    filtered_courses = scraper.filter_courses(all_course_data, selected_courses)

    # Create a dictionary to group courses by type and title
    courses_by_type_and_title = {}

    # Group the courses by type and title and filter courses with seats available
    for course in filtered_courses:
        course_title = f"{course[0]} {course[4]}"
        if course_title not in courses_by_type_and_title:
            courses_by_type_and_title[course_title] = []
        if course[9] == "Seats Available":
            courses_by_type_and_title[course_title].append(course)
    output_file = "course_schedule.txt"

    with open(output_file, "w", encoding="utf-8") as file:
        # Print the courses grouped by type and title
        for course_title, courses in courses_by_type_and_title.items():

            for course in courses:
                print(f"Course: {course_title}, {courses[0][2]}", file=file)
                print(f"Days: {course[5]}\nTimes: {course[6]}\nLocation: {course[7]}\nProfessor: {course[8]}", file=file)
                print('---', file=file)
    print()
    scraper.combo_generator.provide_combinations()


if __name__ == "__main__":
    main()
