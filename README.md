# CSULB Schedule Generator
The CSULB Schedule Generator is a Python project that is designed to streamline the process of creating a personalized course schedule for your academic semester. It accomplishes this by scraping information from CSULB's course catalog and then generating all possible combinations of schedules while ensuring that there are no time conflicts in between each course.

The process of finding and enrolling for courses at CSULB can be time-consuming and at times frustrating. A student registering for classes must make sure that each course does not have any time conflicts with the other and they also have to make sure that each course has seats available in the first place. 

The goal of this generator is to make schedule planning for CSULB easier and registering for courses faster. With this tool, students can save their time registering for classes without having to worry about any time conflicts and seat availability.

## How It Works
* The generator utilizes web scraping to fetch course information from CSULB's course catalog.
* It parses HTML content from each webpage using BeautifulSoup to extract relevant data.
* Every course's information (course code, title, units, class number, course type, days, times, location, instructor, etc.) is saved to a text file.
* The data is also stored in a SQLite database for later use.
* You can filter the course data by selecting certain courses you want to take.
* After doing so, the generator interefaces with the "combo_generator" module to provide schedule combinations of available courses that avoid time conflicts.

### Disclaimer
This project was created for educational/demonstrative purposes. 
I have no affiliation with any of CSULB's sites and neither I nor the software will be held liable for any consequences resulting from its use. 
I take no responsibility for what others do with the code and do not advise for insane scraping of websites.
