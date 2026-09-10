import { useState, useEffect, useRef } from "react";
import type { DiningCourtCategory, LocationMenuData, Meal } from "../types";
import { getLocationMenu } from "../api";
import MealSelector, { type MealName } from "./MealSelector";
import DiningCourtMultiSelector from "./DiningCourtMultiSelector";
import DateSelector from "./DateSelector";
import StationCard from "./StationCard";

function getTodayIso(): string {
  return new Date().toISOString().split("T")[0];
}

interface CourtResult {
  name: string;
  formalName: string;
  data: LocationMenuData | null;
  error: string | null;
}

interface Props {
  categories: DiningCourtCategory[];
}

export default function CompareView({ categories }: Props) {
  const [meal, setMeal] = useState<MealName>("Dinner");
  const [selectedCourts, setSelectedCourts] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(getTodayIso());
  const [results, setResults] = useState<CourtResult[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const formalNameFor = (name: string): string => {
    for (const cat of categories) {
      for (const c of cat.diningCourts) {
        if (c.name === name) return c.formalName;
      }
    }
    return name;
  };

  useEffect(() => {
    if (selectedCourts.length === 0) {
      return;
    }

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);

    Promise.all(
      selectedCourts.map(async (name) => {
        try {
          const data = await getLocationMenu(name, selectedDate);
          return { name, formalName: formalNameFor(name), data, error: null as string | null };
        } catch (err) {
          return {
            name,
            formalName: formalNameFor(name),
            data: null,
            error: err instanceof Error ? err.message : "Failed to fetch",
          };
        }
      })
    )
      .then((res) => {
        if (!ac.signal.aborted) setResults(res);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });

    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCourts, selectedDate]);

  const effectiveResults =
    selectedCourts.length === 0 ? [] : results;

  const findMeal = (data: LocationMenuData | null): Meal | null => {
    if (!data?.diningCourtByName?.dailyMenu) return null;
    const meals = data.diningCourtByName.dailyMenu.meals;
    return meals.find((m) => m.name === meal) ?? null;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-6">
        <div className="sm:w-64 flex-shrink-0">
          <MealSelector selected={meal} onChange={setMeal} />
        </div>
        <div>
          <DateSelector selectedDate={selectedDate} onChange={setSelectedDate} />
        </div>
        <DiningCourtMultiSelector
          categories={categories}
          selected={selectedCourts}
          onChange={setSelectedCourts}
        />
      </div>

      {loading && (
        <div className="text-center py-16 animate-fade-in-up">
          <div className="inline-block h-9 w-9 animate-spin rounded-full border-[3px] border-solid border-gold-dim border-t-gold" />
          <p className="mt-4 font-body text-text-secondary text-sm">
            Loading {meal.toLowerCase()} menus...
          </p>
        </div>
      )}

      {!loading && selectedCourts.length === 0 && (
        <div className="text-center py-16 animate-fade-in-up">
          <p className="font-display text-xl text-text-secondary">
            Select one or more dining courts
          </p>
          <p className="font-body text-sm text-text-muted mt-2">
            Choose locations to compare {meal.toLowerCase()} options
          </p>
        </div>
      )}

      {!loading && selectedCourts.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
          {effectiveResults.map((res, i) => {
            const mealData = findMeal(res.data);
            const isOpen = mealData ? mealData.status.toLowerCase() !== "closed" : false;
            return (
              <div
                key={res.name}
                className="animate-fade-in-up"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <div className="rounded-xl border border-border-subtle bg-surface-1/60 backdrop-blur-sm p-5 h-full">
                  <div className="mb-4">
                    <h3 className="font-display text-xl font-bold text-text-primary">
                      {res.formalName}
                    </h3>
                    <div className="w-12 h-0.5 bg-gradient-to-r from-gold to-transparent mt-2" />
                  </div>

                  {res.error && (
                    <p className="font-body text-sm text-red-badge-text/80 italic">
                      Failed to load: {res.error}
                    </p>
                  )}

                  {!res.error && !mealData && (
                    <p className="font-body text-sm text-text-muted italic">
                      No {meal} served at this court.
                    </p>
                  )}

                  {!res.error && mealData && !isOpen && (
                    <p className="font-body text-sm text-text-muted italic">
                      Closed for {meal.toLowerCase()}.
                    </p>
                  )}

                  {!res.error && mealData && isOpen && mealData.stations.length === 0 && (
                    <p className="font-body text-sm text-text-muted italic">
                      No stations available.
                    </p>
                  )}

                  {!res.error && mealData && isOpen && mealData.stations.length > 0 && (
                    <div className="space-y-3">
                      {mealData.stations.map((station) => (
                        <StationCard key={station.name} station={station} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}