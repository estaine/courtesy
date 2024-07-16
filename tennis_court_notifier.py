import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import calendar

# Configuration

target_timeslots = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30"]  # Add more timeslots as needed
target_clubs = ["mera", "wtc"]  # Add more clubs as needed

# URL template
url_template = "https://kluby.org/{clubName}/grafik?data_grafiku={date}&dyscyplina=1&strona={page}"

# Headers to mimic a real browser request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

court_mapping = {
    "13": "1 (hard)",
    "14": "2 (hard)",
    "15": "3 (hard)",
    "12": "4 (clay)",
    "11": "5 (clay)",
    "10": "6 (clay)",
    "9": "7 (open clay)",
    "8": "8 (open clay)",
    "7": "9 (open clay)",
    "1299": "10 (open clay)",
    "1300": "11 (open clay)",
    "1301": "12 (open clay)",
    "509": "1 (clay)",
    "510": "2 (clay)",
    "511": "3 (clay)",
    "687": "4 (open clay)"

}

club_mapping = {
    "mera": "Mera",
    "wtc": "Wola"
}

def get_next_working_days(num_days):
    days = []
    current_date = datetime.utcnow().date()

    while len(days) < num_days:
        if current_date.weekday() < 5:  # Monday to Friday (0 to 4)
            days.append(current_date.strftime('%Y-%m-%d'))

        current_date += timedelta(days=1)

    return days[:num_days]


target_dates = get_next_working_days(6)  # Add more dates as needed


def format_date(date):
    return f"{calendar.month_name[date.month]} {date.day} ({calendar.day_name[date.weekday()]})"


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
                        technical_court_number = td.find('a')['href'].split('/')[-2]
                        real_court_number = court_mapping.get(technical_court_number, f"Unknown court {technical_court_number}")
                        available_courts.append(real_court_number)

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


def extract_court_number(court):
    return int(court.split()[0])


def send_telegram_message(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    response = requests.post(url, data=payload)
    return response



if __name__ == "__main__":
    available_slots = check_availability()

    # Group results by date and club
    grouped_results = {}
    for result in available_slots:
        if isinstance(result['date'], str):
            result['date'] = datetime.strptime(result['date'], '%Y-%m-%d').date()

        date_str = format_date(result['date'])
        club_name = club_mapping.get(result['club'], result['club'])
        if date_str not in grouped_results:
            grouped_results[date_str] = {}
        if club_name not in grouped_results[date_str]:
            grouped_results[date_str][club_name] = {}

        for info in result['availability_info']:
            timeslot = info['timeslot']
            for court in info['available_courts']:
                if court not in grouped_results[date_str][club_name]:
                    grouped_results[date_str][club_name][court] = set()
                grouped_results[date_str][club_name][court].add(timeslot)

    # Format the message
    message_lines = []
    for date, clubs in sorted(grouped_results.items()):
        message_lines.append(f"<b>{date_str}</b>")
        for club, courts in sorted(clubs.items()):
            # Sort courts by numeric value
            sorted_courts = sorted(courts.items(), key=lambda x: int(x[0].split()[0]))

            for court, timeslots in sorted_courts:
                message_lines.append(f"{club}, Court {court}: {', '.join(sorted(timeslots))}")
        message_lines.append("")  # Add an empty line for separation

    message = "\n".join(message_lines).strip()
    if message:
        send_telegram_message(message)
    else:
        send_telegram_message("No available slots found.")
