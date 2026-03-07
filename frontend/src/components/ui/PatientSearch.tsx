"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { searchPatients } from "@/lib/api";
import type { PatientSearchResult } from "@/lib/types";

interface Props {
  selectedPatientId: string | null;
  onSelect: (patientId: string) => void;
  disabled?: boolean;
  id?: string;
  placeholder?: string;
}

/**
 * Search-as-you-type combobox for patient IDs.
 * Calls /api/patients/search with debounce — never loads all 196K into the DOM.
 */
export default function PatientSearch({
  selectedPatientId,
  onSelect,
  disabled = false,
  id = "patient-search",
  placeholder = "Search patient ID...",
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PatientSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Debounced search
  const doSearch = useCallback(
    (q: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        setLoading(true);
        try {
          const res = await searchPatients(q, 20);
          setResults(res.results);
          setIsOpen(true);
          setHighlightIdx(-1);
        } catch {
          setResults([]);
        } finally {
          setLoading(false);
        }
      }, 200);
    },
    [],
  );

  // On input change
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    doSearch(val);
  };

  // On selecting a result
  const handleSelect = (pid: string) => {
    setQuery("");
    setIsOpen(false);
    setHighlightIdx(-1);
    onSelect(pid);
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || results.length === 0) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        doSearch(query);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && highlightIdx >= 0) {
      e.preventDefault();
      handleSelect(results[highlightIdx].patient_id);
    } else if (e.key === "Escape") {
      setIsOpen(false);
      setHighlightIdx(-1);
    }
  };

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightIdx >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll("li");
      items[highlightIdx]?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightIdx]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const displayValue = selectedPatientId ? `Patient ${selectedPatientId}` : "";

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <input
        ref={inputRef}
        id={id}
        type="text"
        className="glass app-select"
        style={{
          width: "100%",
          cursor: disabled ? "not-allowed" : "text",
          fontSize: "0.85rem",
        }}
        value={isOpen ? query : displayValue}
        onChange={handleChange}
        onFocus={() => {
          setQuery("");
          doSearch("");
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={`${id}-listbox`}
        aria-activedescendant={
          highlightIdx >= 0 ? `${id}-option-${highlightIdx}` : undefined
        }
      />

      {isOpen && (
        <ul
          ref={listRef}
          id={`${id}-listbox`}
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 50,
            maxHeight: 280,
            overflowY: "auto",
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: "rgba(26, 29, 39, 0.97)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            marginTop: 4,
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
          }}
        >
          {loading && (
            <li style={{ padding: "10px 14px", color: "#8892A4", fontSize: "0.82rem" }}>
              Searching...
            </li>
          )}
          {!loading && results.length === 0 && (
            <li style={{ padding: "10px 14px", color: "#8892A4", fontSize: "0.82rem" }}>
              No patients found
            </li>
          )}
          {!loading &&
            results.map((r, idx) => (
              <li
                key={r.patient_id}
                id={`${id}-option-${idx}`}
                role="option"
                aria-selected={highlightIdx === idx}
                onClick={() => handleSelect(r.patient_id)}
                style={{
                  padding: "8px 14px",
                  cursor: "pointer",
                  fontSize: "0.84rem",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  background:
                    highlightIdx === idx
                      ? "rgba(79, 195, 247, 0.12)"
                      : r.patient_id === selectedPatientId
                        ? "rgba(79, 195, 247, 0.06)"
                        : "transparent",
                  color: r.patient_id === selectedPatientId ? "#4FC3F7" : "#E8E8E8",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                }}
                onMouseEnter={() => setHighlightIdx(idx)}
              >
                <span>Patient {r.patient_id}</span>
                <span style={{ color: "#8892A4", fontSize: "0.75rem" }}>
                  {r.age != null && `${r.age}y`}
                  {r.age != null && r.sex && " / "}
                  {r.sex}
                </span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
