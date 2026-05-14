export interface Trait {
  name: string;
}

export interface MenuItem {
  name: string;
  traits: Trait[];
}

export interface StationItem {
  item: MenuItem | null;
}

export interface Station {
  name: string;
  items: StationItem[];
}

export interface Meal {
  name: string;
  status: string;
  stations: Station[];
}

export interface DailyMenu {
  meals: Meal[];
}

export interface DiningCourt {
  name: string;
  formalName: string;
}

export interface DiningCourtCategory {
  name: string;
  diningCourts: DiningCourt[];
}

export interface LocationMenuData {
  diningCourtByName: {
    formalName: string;
    dailyMenu: DailyMenu | null;
  } | null;
}