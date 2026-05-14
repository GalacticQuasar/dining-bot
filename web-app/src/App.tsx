import { useState, useEffect, useRef } from "react";
import type { DiningCourtCategory, DiningCourt, LocationMenuData } from "./types";
import { getStartLocations, getLocationMenu } from "./api";
import DiningCourtSelector from "./components/DiningCourtSelector";
import DateSelector from "./components/DateSelector";
import MenuDisplay from "./components/MenuDisplay";

function getTodayIso(): string {
  return new Date().toISOString().split("T")[0];
}

export default function App() {
  const [categories, setCategories] = useState<DiningCourtCategory[]>([]);
  const [selectedCourt, setSelectedCourt] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>(getTodayIso());
  const [menuData, setMenuData] = useState<LocationMenuData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [courtName, setCourtName] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getStartLocations()
      .then(setCategories)
      .catch((err) => setError(err.message));
  }, []);

  async function fetchMenu(court: string, date: string) {
    if (!court || !date) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);
    try {
      const data = await getLocationMenu(court, date);
      if (!ac.signal.aborted) {
        setMenuData(data);
      }
    } catch (err) {
      if (!ac.signal.aborted) {
        setError(err instanceof Error ? err.message : "Failed to fetch menu");
        setMenuData(null);
      }
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
      }
    }
  }

  const handleCourtChange = (court: DiningCourt) => {
    setSelectedCourt(court.name);
    setCourtName(court.formalName);
    fetchMenu(court.name, selectedDate);
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    if (selectedCourt) {
      fetchMenu(selectedCourt, date);
    }
  };

  return (
    <div className="min-h-screen bg-surface-0">
      <header className="relative overflow-hidden border-b border-border-gold bg-surface-1">
        <div className="absolute inset-0 bg-gradient-to-r from-gold-muted via-transparent to-gold-muted" />
        <div className="relative max-w-5xl mx-auto px-6 py-8 sm:py-10">
          <div className="flex items-end gap-4">
            <div>
              <p className="font-body text-xs font-medium tracking-[0.3em] uppercase text-gold-dim mb-2">
                Purdue University
              </p>
              <h1 className="font-display text-4xl sm:text-5xl font-bold text-text-primary leading-none">
                Dining
              </h1>
            </div>
            <div className="h-px flex-1 bg-gradient-to-r from-border-gold to-transparent mb-3" />
          </div>
          <p className="font-body text-sm text-text-secondary mt-2">
            Browse dining court menus across campus
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex flex-col sm:flex-row gap-6 mb-8 animate-fade-in-up">
          <div className="sm:w-64 flex-shrink-0">
            <DiningCourtSelector
              categories={categories}
              selected={selectedCourt}
              onChange={handleCourtChange}
            />
          </div>
          <div className="flex-1 min-w-0">
            <DateSelector
              selectedDate={selectedDate}
              onChange={handleDateChange}
            />
          </div>
        </div>

        {error && (
          <div className="bg-red-badge/30 border border-red-badge-text/20 rounded-xl p-4 mb-6 animate-fade-in-up">
            <p className="font-body font-medium text-red-badge-text">Error</p>
            <p className="font-body text-sm text-red-badge-text/70 mt-1">{error}</p>
          </div>
        )}

        {loading && (
          <div className="text-center py-16 animate-fade-in-up">
            <div className="inline-block h-9 w-9 animate-spin rounded-full border-[3px] border-solid border-gold-dim border-t-gold" />
            <p className="mt-4 font-body text-text-secondary text-sm">
              Loading menu{courtName ? ` for ${courtName}` : ""}...
            </p>
          </div>
        )}

        {!loading && selectedCourt && !error && (
          <div className="animate-fade-in-up">
            <MenuDisplay data={menuData} />
          </div>
        )}

        {!selectedCourt && !loading && (
          <div className="text-center py-24 animate-fade-in-up">
            <div className="inline-block w-16 h-16 rounded-full border border-border-gold bg-gold-muted mb-6 flex items-center justify-center">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-gold">
                <path d="M3 12h18M3 6h18M3 18h18" strokeLinecap="round" />
              </svg>
            </div>
            <p className="font-display text-xl text-text-secondary">
              Select a dining court
            </p>
            <p className="font-body text-sm text-text-muted mt-2">
              Choose a location to view today's menu
            </p>
          </div>
        )}
      </main>

      <footer className="border-t border-border-subtle mt-12">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <p className="font-body text-xs text-text-muted text-center">
            Data from Purdue Dining & Culinary Services
          </p>
        </div>
      </footer>
    </div>
  );
}