"use client";

import { useEffect, useState } from "react";

import { CredentialsForm } from "@/components/CredentialsForm";
import { MarkdownPreview } from "@/components/MarkdownPreview";
import {
  clearStoredAccessToken,
  exportBatchFile,
  exportBatchMarkdown,
  exportMarkdown,
  getStoredAccessToken,
  getRecentActivities,
  loginToGarmin,
  logoutFromGarmin,
  storeAccessToken,
} from "@/lib/api";
import type {
  ApiError,
  ExportFormValues,
  RecentActivitySummary,
} from "@/lib/types";

const initialValues: ExportFormValues = {
  email: "",
  password: "",
  mode: "single_activity",
  selectedActivityIds: [],
  batchExportFormat: "zip",
  dateFrom: "",
  dateTo: "",
  maxActivities: "10",
  notes: "",
};

function isApiError(error: unknown): error is ApiError {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    "message" in error
  );
}

export default function Home() {
  const [values, setValues] = useState<ExportFormValues>(initialValues);
  const [markdown, setMarkdown] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [authenticated, setAuthenticated] = useState<boolean>(() => Boolean(getStoredAccessToken()));
  const [authMessage, setAuthMessage] = useState<string>("");
  const [activities, setActivities] = useState<RecentActivitySummary[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState<boolean>(false);
  const [activitiesError, setActivitiesError] = useState<string>("");
  const [resultMessage, setResultMessage] = useState<string>("");

  function downloadBlob(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  async function loadRecentActivities() {
    if (!getStoredAccessToken()) {
      setAuthenticated(false);
      setActivities([]);
      setActivitiesError("Connecte-toi pour charger les activites recentes.");
      return;
    }

    setActivitiesLoading(true);
    setActivitiesError("");

    try {
      const recentActivities = await getRecentActivities();
      setAuthenticated(true);
      setActivities(recentActivities);
      setValues((currentValues) => {
        if (currentValues.mode === "date_range") {
          return currentValues;
        }

        const currentSelections = currentValues.selectedActivityIds.filter((activityId) =>
          recentActivities.some((activity) => activity.activity_id === activityId),
        );
        const nextSelectedActivityIds =
          currentSelections.length > 0 || recentActivities.length === 0
            ? currentSelections
            : recentActivities[0]
              ? [recentActivities[0].activity_id]
              : [];

        return nextSelectedActivityIds.join(",") === currentValues.selectedActivityIds.join(",")
          ? currentValues
          : { ...currentValues, selectedActivityIds: nextSelectedActivityIds };
      });
    } catch (caughtError: unknown) {
      setActivities([]);
      setValues((currentValues) =>
        currentValues.selectedActivityIds.length > 0
          ? { ...currentValues, selectedActivityIds: [] }
          : currentValues,
      );
      if (isApiError(caughtError)) {
        if (caughtError.status === 401) {
          clearStoredAccessToken();
          setAuthenticated(false);
          setActivitiesError("Connecte-toi pour charger les activites recentes.");
        } else {
          setActivitiesError(caughtError.message);
        }
      } else if (caughtError instanceof Error) {
        setActivitiesError(caughtError.message);
      } else {
        setActivitiesError("Impossible de charger les activites recentes.");
      }
    } finally {
      setActivitiesLoading(false);
    }
  }

  useEffect(() => {
    if (values.mode === "date_range") {
      return;
    }

    if (!getStoredAccessToken()) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void loadRecentActivities();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [values.mode]);

  async function handleLogin(formValues: ExportFormValues) {
    setAuthLoading(true);
    setAuthMessage("");
    setError("");
    setResultMessage("");

    try {
      const response = await loginToGarmin({
        email: formValues.email.trim(),
        password: formValues.password,
      });
      storeAccessToken(response.access_token);
      setAuthenticated(true);
      setAuthMessage("Connexion Garmin active.");
      await loadRecentActivities();
    } catch (caughtError: unknown) {
      clearStoredAccessToken();
      setAuthenticated(false);
      setActivities([]);
      if (isApiError(caughtError)) {
        setAuthMessage(caughtError.message);
      } else if (caughtError instanceof Error) {
        setAuthMessage(caughtError.message);
      } else {
        setAuthMessage("La connexion Garmin a echoue.");
      }
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    if (!getStoredAccessToken()) {
      setAuthenticated(false);
      setAuthMessage("Aucune session Garmin active.");
      return;
    }

    setAuthLoading(true);
    setError("");
    setResultMessage("");

    try {
      const response = await logoutFromGarmin();
      clearStoredAccessToken();
      setAuthenticated(false);
      setActivities([]);
      setActivitiesError("Connecte-toi pour charger les activites recentes.");
      setMarkdown("");
      setValues((currentValues) => ({
        ...currentValues,
        selectedActivityIds: [],
      }));
      setAuthMessage(response.message);
    } catch (caughtError: unknown) {
      if (isApiError(caughtError) && caughtError.status === 401) {
        clearStoredAccessToken();
        setAuthenticated(false);
        setActivities([]);
        setActivitiesError("Connecte-toi pour charger les activites recentes.");
      }
      if (isApiError(caughtError)) {
        setAuthMessage(caughtError.message);
      } else if (caughtError instanceof Error) {
        setAuthMessage(caughtError.message);
      } else {
        setAuthMessage("La deconnexion Garmin a echoue.");
      }
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleSubmit(formValues: ExportFormValues) {
    if (!authenticated || !getStoredAccessToken()) {
      setError("Connecte-toi d'abord a Garmin.");
      return;
    }

    setLoading(true);
    setError("");
    setMarkdown("");
    setResultMessage("");

    try {
      const commonPayload = {
        notes: formValues.notes.trim() || undefined,
        include_notes: true,
      };
      if (formValues.mode === "single_activity") {
        const activityId = formValues.selectedActivityIds[0];
        if (!activityId) {
          setError("Selectionne une activite.");
          return;
        }

        const response = await exportMarkdown({
          ...commonPayload,
          mode: "single_activity",
          activity_id: activityId,
        });
        setMarkdown(response.markdown);
        return;
      }

      if (formValues.mode === "multi_activity") {
        if (formValues.selectedActivityIds.length === 0) {
          setError("Selectionne au moins une activite.");
          return;
        }

        const download = await exportBatchFile({
          ...commonPayload,
          activity_ids: formValues.selectedActivityIds,
          export_format: formValues.batchExportFormat,
        });
        downloadBlob(download.blob, download.filename);
        setResultMessage(
          `${formValues.selectedActivityIds.length} fichier(s) exporte(s) dans ${download.filename}.`,
        );
        return;
      }

      const response = await exportBatchMarkdown({
        ...commonPayload,
        mode: "date_range",
        date_from: formValues.dateFrom,
        date_to: formValues.dateTo,
        max_activities: Number.parseInt(formValues.maxActivities, 10),
        activity_type: "running",
      });
      setMarkdown(response.markdown);
    } catch (caughtError: unknown) {
      if (isApiError(caughtError)) {
        if (caughtError.status === 401) {
          clearStoredAccessToken();
          setAuthenticated(false);
          setActivities([]);
        }
        setError(caughtError.message);
      } else if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("La generation Markdown a echoue.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="workspace">
        <div className="intro">
          <p className="eyebrow">Garmin vers Markdown</p>
          <h1>Exporter une activite Garmin</h1>
          <p>
            Entre les informations Garmin, puis choisis une activite precise ou une plage de
            dates pour obtenir un Markdown pret a analyser.
          </p>
        </div>

        <CredentialsForm
          values={values}
          loading={loading}
          authLoading={authLoading}
          authenticated={authenticated}
          authMessage={authMessage}
          activities={activities}
          activitiesLoading={activitiesLoading}
          activitiesError={activitiesError}
          onChange={setValues}
          onLogin={handleLogin}
          onLogout={handleLogout}
          onSubmit={handleSubmit}
        />

        {error ? <p className="error-message">{error}</p> : null}
        {resultMessage ? <p className="status-message">{resultMessage}</p> : null}
        {markdown ? <MarkdownPreview markdown={markdown} /> : null}
      </section>
    </main>
  );
}
