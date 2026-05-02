import requests
from datetime import date

DINING_API_URL = "https://api.hfs.purdue.edu/menus/v3/GraphQL"

def get_start_locations():
    """Fetches the list of all dining locations and their availability"""
    query = """
    query getStartLocations {
      diningCourtCategories {
        name
        diningCourts {
          name
          formalName
        }
      }
    }
    """
    payload = {"operationName": "getStartLocations", "query": query, "variables": {}}
    headers = {"Content-Type": "application/json"}

    response = requests.post(DINING_API_URL, json=payload, headers=headers)
    return response.json().get('data', {}).get('diningCourtCategories', [])

def get_location_menu(court_name, date_str):
    """Fetches the menu for a specific dining location"""
    query = """
    query getLocationMenu($name: String!, $date: Date!) {
      diningCourtByName(name: $name) {
        formalName
        dailyMenu(date: $date) {
          meals {
            name
            status
            stations {
              name
              items {
                item {
                  name
                  traits {
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "operationName": "getLocationMenu",
        "query": query,
        "variables": {"name": court_name, "date": date_str}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(DINING_API_URL, json=payload, headers=headers)
    return response.json()

def parse_and_print_menu(data):
    """Simple parser to display the returned JSON data with null safety"""
    if not data or 'data' not in data or not data['data']['diningCourtByName']:
        print("No valid data found.")
        return

    court = data['data']['diningCourtByName']
    print(f"--- {court['formalName']} Menu ---")

    # dailyMenu or meals could also be null if the court is closed
    daily_menu = court.get('dailyMenu')
    if not daily_menu:
        print("No menu available for this date.")
        return

    for meal in daily_menu.get('meals', []):
        print(f"\n[ {meal['name']} ] - Status: {meal['status']}")

        for station in meal.get('stations', []):
            print(f"  Station: {station['name']}")
            for menu_item in station.get('items', []):
                item = menu_item.get('item')
                if not item:
                    continue

                # use .get('traits') or [] so that if it is None, we have an empty list
                item_traits = item.get('traits') or []
                traits = [t['name'] for t in item_traits]

                trait_str = f" ({', '.join(traits)})" if traits else ""
                print(f"    - {item['name']}{trait_str}")

def main():
    print("Fetching dining locations...")
    categories = get_start_locations()

    all_courts = []
    print("\nDining Locations:")
    for cat in categories:
        print(f"\n  {cat['name']}")
        for court in cat['diningCourts']:
            idx = len(all_courts)
            all_courts.append(court)
            print(f"    {idx + 1}. {court['formalName']}")

    choice = int(input("\nEnter the number of your choice: ")) - 1
    selected_court = all_courts[choice]['name']

    date_str = date.today().isoformat()  # use today's date for now

    print(f"\nFetching menu for {selected_court} on {date_str}...")
    menu_data = get_location_menu(selected_court, date_str)

    parse_and_print_menu(menu_data)

if __name__ == "__main__":
    main()
