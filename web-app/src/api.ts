import type { DiningCourtCategory, LocationMenuData } from "./types";

const API_URL = "/api/menus/v3/GraphQL";

async function graphqlRequest<T>(
  operationName: string,
  query: string,
  variables: Record<string, unknown> = {}
): Promise<T> {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operationName, query, variables }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  const json = await response.json();
  if (json.errors) {
    throw new Error(json.errors.map((e: { message: string }) => e.message).join(", "));
  }

  return json.data as T;
}

const START_LOCATIONS_QUERY = `
  query getStartLocations {
    diningCourtCategories {
      name
      diningCourts {
        name
        formalName
      }
    }
  }
`;

const LOCATION_MENU_QUERY = `
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
`;

export async function getStartLocations(): Promise<DiningCourtCategory[]> {
  const data = await graphqlRequest<{ diningCourtCategories: DiningCourtCategory[] }>(
    "getStartLocations",
    START_LOCATIONS_QUERY
  );
  return data.diningCourtCategories;
}

export async function getLocationMenu(
  courtName: string,
  dateStr: string
): Promise<LocationMenuData> {
  return graphqlRequest<LocationMenuData>("getLocationMenu", LOCATION_MENU_QUERY, {
    name: courtName,
    date: dateStr,
  });
}