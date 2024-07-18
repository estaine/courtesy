import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import calendar
import psycopg2
import json

# Configuration
target_timeslots = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30"]  # Add more timeslots as needed

# URL template
url_template = "https://kluby.org/{clubName}/grafik?data_grafiku={date}&dyscyplina=1&strona={page}"

# Headers to mimic a real browser request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

def fetch_data_from_db():
    connection = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        dbname=os.getenv('DB_NAME')
    )

    cursor = connection.cursor()

    # Fetch clubs
    cursor.execute("SELECT key, name FROM club")
    clubs = cursor.fetchall()
    target_clubs = [club[0] for club in clubs]
    club_mapping = {key: name for key, name in clubs}

    # Fetch courts
    cursor.execute("SELECT internal_id, surface, open, number FROM court")
    courts = cursor.fetchall()
    court_mapping = {
        str(court[0]): {
            "surface": court[1],
            "open": court[2],
            "number": court[3]
        } for court in courts
    }

    connection.close()

    return target_clubs, court_mapping, club_mapping

def get_bookings():
    connection = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        dbname=os.getenv('DB_NAME')
    )

    cursor = connection.cursor()

    # Fetch all bookings
    cursor.execute("SELECT id, data FROM booking WHERE actual = true")
    bookings_data = cursor.fetchall()

    current_date = datetime.utcnow().date()
    active_bookings = []

    for booking_id, booking_json in bookings_data:
        booking = booking_json
        booking_date = datetime.strptime(booking['date'], '%Y-%m-%d').date()

        if booking_date < current_date:
            # Update actual to false for past bookings
            cursor.execute("UPDATE booking SET actual = false WHERE id = %s", (booking_id,))
        else:
            active_bookings.append(booking)

    connection.commit()
    connection.close()

    return active_bookings

target_clubs, court_mapping, club_mapping = fetch_data_from_db()

def get_next_working_days(num_days):
    days = []
    current_date = datetime.utcnow().date()

    while len(days) < num_days:
        if current_date.weekday() < 5:  # Monday to Friday (0 to 4)
            days.append(current_date.strftime('%Y-%m-%d'))

        current_date += timedelta(days=1)

    return days[:num_days]

target_dates = get_next_working_days(6)  # Add more dates as needed


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
                        court_info = court_mapping.get(technical_court_number)
                        if court_info:
                            court_type = court_info['surface'].capitalize()
                            if court_info['open']:
                                court_type = f"Open {court_type}"
                            real_court_number = f"{court_type} (court {court_info['number']})"
                            available_courts.append({
                                "court_id": technical_court_number,
                                "real_court_number": real_court_number,
                                "type": court_info["surface"],
                                "open": court_info["open"],
                                "number": court_info["number"]
                            })

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

def format_available_slots(available_slots):
    grouped_results = {}

    # Group results by date and club
    for slot in available_slots:
        date_str = slot['date']
        club_name = club_mapping.get(slot['club'], slot['club'])
        if date_str not in grouped_results:
            grouped_results[date_str] = {}

        if club_name not in grouped_results[date_str]:
            grouped_results[date_str][club_name] = {}

        for court_info in slot['availability_info']:
            timeslot = court_info['timeslot']
            available_courts = court_info['available_courts']

            for court in available_courts:
                court_name = court['real_court_number']

                if court_name not in grouped_results[date_str][club_name]:
                    grouped_results[date_str][club_name][court_name] = []

                grouped_results[date_str][club_name][court_name].append(timeslot)

    # Merge time slots into continuous intervals of 30 minutes
    merged_results = {}
    for date, clubs in grouped_results.items():
        merged_results[date] = {}
        for club, courts in clubs.items():
            merged_results[date][club] = {}
            for court, timeslots in courts.items():
                merged_timeslots = []
                timeslots.sort()  # Sort timeslots chronologically

                start_time = None
                end_time = None

                for time_str in timeslots:
                    time_obj = datetime.strptime(time_str, '%H:%M')
                    if start_time is None:
                        start_time = time_obj
                        end_time = time_obj + timedelta(minutes=30)
                    elif time_obj <= end_time:
                        end_time = time_obj + timedelta(minutes=30)
                    else:
                        merged_timeslots.append(f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
                        start_time = time_obj
                        end_time = start_time + timedelta(minutes=30)

                # Append the last interval
                if start_time is not None and end_time is not None:
                    merged_timeslots.append(f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")

                merged_results[date][club][court] = merged_timeslots

    return merged_results

def filter_by_bookings(merged_results, booking):
    filtered_results = {}

    date = booking['date']
    start_time_min = datetime.strptime(booking['start_time_min'], '%H:%M')
    start_time_max = datetime.strptime(booking['start_time_max'], '%H:%M')
    duration = timedelta(hours=booking['duration'])
    quantity = booking['quantity']
    open_courts_only = booking.get('open', [True, False])

    if date not in merged_results:
        return filtered_results

    filtered_results[date] = {}

    for club, courts in merged_results[date].items():
        for court, timeslots in courts.items():
            is_open_court = 'Open' in court
            if is_open_court not in open_courts_only:
                continue

            for timeslot in timeslots:
                start_time_str, end_time_str = timeslot.split(' - ')
                start_time = datetime.strptime(start_time_str, '%H:%M')
                end_time = datetime.strptime(end_time_str, '%H:%M')

                if start_time < start_time_min or end_time > start_time_max:
                    continue

                if end_time - start_time >= duration:
                    start_times = [start_time + timedelta(minutes=30 * i) for i in range(0, int((end_time - start_time).total_seconds() // 1800))]
                    for st in start_times:
                        et = st + duration
                        if et > start_time_max:
                            break
                        timeslot_str = f"{st.strftime('%H:%M')} - {et.strftime('%H:%M')}"
                        if club not in filtered_results[date]:
                            filtered_results[date][club] = {}
                        if timeslot_str not in filtered_results[date][club]:
                            filtered_results[date][club][timeslot_str] = []
                        filtered_results[date][club][timeslot_str].append(court)

    final_results = {}
    for date, clubs in filtered_results.items():
        final_results[date] = {}
        for club, timeslots in clubs.items():
            final_results[date][club] = {}
            for timeslot, courts in timeslots.items():
                if len(courts) >= quantity:
                    final_results[date][club][timeslot] = courts

    return final_results

def format_date(date_str):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{date_obj.strftime('%B %d')} ({date_obj.strftime('%A')})"

def format_duration(duration):
    hours = int(duration)
    minutes = int((duration - hours) * 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"

def format_surface(surface):
    if not surface or surface == ['clay', 'hard']:
        return "Any"
    return ", ".join(surface).capitalize()

def format_roofed(open):
    if not open or open == [True, False]:
        return "Any"
    return "No" if open == [True] else "Yes"

def format_message(bookings, merged_results):
    message_lines = []

    for booking in sorted(bookings, key=lambda x: x['date']):
        date = booking['date']
        formatted_date = format_date(date)
        start_time_range = f"{booking['start_time_min']} - {booking['start_time_max']}"
        surface = format_surface(booking.get('surface'))
        roofed = format_roofed(booking.get('open'))
        duration = format_duration(booking['duration'])
        quantity = booking['quantity']

        message_lines.append(f"<b>Requested:</b>")
        message_lines.append(f"Date: {formatted_date}")
        message_lines.append(f"Start time range: {start_time_range}")
        message_lines.append(f"Surface: {surface}")
        message_lines.append(f"Roofed: {roofed}")
        message_lines.append(f"Duration: {duration}")
        message_lines.append(f"Number of courts: {quantity}")
        message_lines.append("")
        message_lines.append(f"<b>Found:</b>")

        booking_results = filter_by_bookings(merged_results, booking)

        if date not in booking_results or not booking_results[date]:
            message_lines.append("No matching slots found")
            message_lines.append("")  # Add an empty line after the message
            continue

        for club, timeslots in sorted(booking_results[date].items()):
            message_lines.append(club)
            for timeslot, courts in sorted(timeslots.items()):
                message_lines.append(f"{timeslot}: {', '.join(courts)}")
            message_lines.append("")  # Add an empty line after each club

    return "\n".join(message_lines).strip()

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

    # Fetch bookings from database
    bookings = get_bookings()

    # Format available slots
    merged_results = format_available_slots(available_slots)

    # Format the message
    message = format_message(bookings, merged_results)

    # Send message to Telegram
    if message:
        send_telegram_message(message)
    else:
        send_telegram_message("No available slots found.")
