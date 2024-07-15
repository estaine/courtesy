import requests
from bs4 import BeautifulSoup

# Configuration
target_dates = ["2024-07-20", "2024-07-21"]  # Add more dates as needed
target_timeslots = ["18:00", "18:30", "19:00", "19:30", "20:00"]  # Add more timeslots as needed
target_clubs = ["mera", "wtc"]  # Add more clubs as needed

# URL template
url_template = "https://kluby.org/{clubName}/grafik?data_grafiku={date}&dyscyplina=1&strona={page}"

# Headers to mimic a real browser request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

def parse_availability(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    results = []

    # Find all <tr> elements where the first <td> looks like a time (e.g., 0:00, 1:00, etc.)
    rows = soup.find_all('tr')
    for row in rows:
        first_td = row.find('td', class_='')
        if first_td and ':' in first_td.text.strip():  # Check if it looks like a time
            # Get all <td> elements within this row
            tds = row.find_all('td')

            # Parse the timeslot from the first <td>
            timeslot = first_td.text.strip()

            if timeslot in target_timeslots:

                # Check availability in subsequent <td> elements (skipping the first one)
                available_courts = []
                for td in tds[1:]:
                    if td.find('a') and 'Rezerwuj' in td.find('a').text:  # Assuming 'Rezerwuj' indicates availability
                        court_number = td.find('a')['href'].split('/')[-2]
                        available_courts.append(court_number)

                if available_courts:
                    results.append({
                        'timeslot': timeslot,
                        'available_courts': available_courts
                    })

    return results

def check_availability():
    results = []
    for club in target_clubs:
        for date in target_dates:
            for page in range(2):  # Iterate over possible values of 'strona' (e.g., 0 and 1)
                url = url_template.format(clubName=club, date=date, page=page)
                response = requests.get(url, headers=headers)

                if response.status_code == 403:
                    print(f"Access forbidden for URL: {url}")
                    continue

                availability_info = parse_availability(response.content)

                if availability_info:
                    results.append({
                        'club': club,
                        'date': date,
                        'page': page,
                        'availability_info': availability_info
                    })

    return results

if __name__ == "__main__":
    available_slots = check_availability()
    for result in available_slots:
        print(f"Club: {result['club']}, Date: {result['date']}, Page: {result['page']}")
        for info in result['availability_info']:
            print(f"Timeslot: {info['timeslot']}, Available Courts: {', '.join(info['available_courts'])}")
