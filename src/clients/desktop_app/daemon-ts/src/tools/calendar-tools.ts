/**
 * Calendar Tools — Google Calendar integration.
 *
 * Ported from google_calendar_toolkit.py.
 *
 * Tools: list_events, create_event, update_event, delete_event,
 *        get_event, get_free_busy, list_calendars, quick_add.
 *
 * Dependencies: googleapis npm package.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("calendar-tools");

// ===== Lazy import googleapis =====

async function getCalendarAPI(credentials: CalendarCredentials) {
  const { google } = await import("googleapis");

  const auth = new google.auth.OAuth2(
    credentials.clientId,
    credentials.clientSecret,
  );

  auth.setCredentials({
    refresh_token: credentials.refreshToken,
    access_token: credentials.accessToken,
  });

  return google.calendar({ version: "v3", auth });
}

// ===== Credentials =====

interface CalendarCredentials {
  clientId: string;
  clientSecret: string;
  refreshToken?: string;
  accessToken?: string;
}

function getCredentials(): CalendarCredentials {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;

  if (!clientId || !clientSecret) {
    throw new Error(
      "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set for calendar tools.",
    );
  }

  return {
    clientId,
    clientSecret,
    refreshToken: process.env.GOOGLE_REFRESH_TOKEN,
    accessToken: process.env.GOOGLE_ACCESS_TOKEN,
  };
}

// ===== Schemas =====

const listEventsSchema = Type.Object({
  max_results: Type.Optional(
    Type.Number({ description: "Maximum events to return. Default: 10." }),
  ),
  time_min: Type.Optional(
    Type.String({
      description:
        "Start time filter (ISO 8601). Default: now.",
    }),
  ),
  time_max: Type.Optional(
    Type.String({ description: "End time filter (ISO 8601)." }),
  ),
});

const createEventSchema = Type.Object({
  title: Type.String({ description: "Event title" }),
  start_time: Type.String({
    description: "Start time in ISO 8601 format (e.g., '2026-02-14T10:00:00')",
  }),
  end_time: Type.String({
    description: "End time in ISO 8601 format",
  }),
  description: Type.Optional(Type.String({ description: "Event description" })),
  location: Type.Optional(Type.String({ description: "Event location" })),
  attendees: Type.Optional(
    Type.Array(Type.String(), {
      description: "Email addresses of attendees",
    }),
  ),
  timezone: Type.Optional(
    Type.String({ description: "Timezone (e.g., 'America/New_York'). Default: UTC." }),
  ),
});

const updateEventSchema = Type.Object({
  event_id: Type.String({ description: "ID of the event to update" }),
  title: Type.Optional(Type.String({ description: "New event title" })),
  start_time: Type.Optional(Type.String({ description: "New start time (ISO 8601)" })),
  end_time: Type.Optional(Type.String({ description: "New end time (ISO 8601)" })),
  description: Type.Optional(Type.String({ description: "New description" })),
  location: Type.Optional(Type.String({ description: "New location" })),
});

const deleteEventSchema = Type.Object({
  event_id: Type.String({ description: "ID of the event to delete" }),
});

const getCalendarSchema = Type.Object({});

const getEventSchema = Type.Object({
  event_id: Type.String({ description: "ID of the event to retrieve" }),
  calendar_id: Type.Optional(
    Type.String({ description: "Calendar ID. Default: 'primary'." }),
  ),
});

const getFreeBusySchema = Type.Object({
  time_min: Type.String({ description: "Start of time range (ISO 8601)" }),
  time_max: Type.String({ description: "End of time range (ISO 8601)" }),
  calendars: Type.Optional(
    Type.Array(Type.String(), {
      description: "Calendar IDs to check. Default: ['primary'].",
    }),
  ),
});

const listCalendarsSchema = Type.Object({});

const quickAddSchema = Type.Object({
  text: Type.String({
    description:
      "Natural language event description (e.g., 'Meeting with John tomorrow at 3pm')",
  }),
  calendar_id: Type.Optional(
    Type.String({ description: "Calendar ID. Default: 'primary'." }),
  ),
});

// ===== Tool Factory =====

export function createCalendarTools(): AgentTool<any>[] {
  const list_events: AgentTool<typeof listEventsSchema> = {
    name: "list_events",
    label: "List Calendar Events",
    description: "List upcoming events from Google Calendar.",
    parameters: listEventsSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);

      const resp = await calendar.events.list({
        calendarId: "primary",
        timeMin: params.time_min ?? new Date().toISOString(),
        timeMax: params.time_max,
        maxResults: params.max_results ?? 10,
        singleEvents: true,
        orderBy: "startTime",
      });

      const events = resp.data.items ?? [];

      if (events.length === 0) {
        return {
          content: [{ type: "text", text: "No upcoming events found." }],
          details: undefined,
        };
      }

      const lines = events.map((e: any) => {
        const start = e.start?.dateTime ?? e.start?.date ?? "?";
        const end = e.end?.dateTime ?? e.end?.date ?? "";
        const location = e.location ? ` | Location: ${e.location}` : "";
        return `- ${e.summary ?? "(No title)"}\n  ${start} → ${end}${location}\n  ID: ${e.id}`;
      });

      return {
        content: [{ type: "text", text: lines.join("\n\n") }],
        details: undefined,
      };
    },
  };

  const create_event: AgentTool<typeof createEventSchema> = {
    name: "create_event",
    label: "Create Calendar Event",
    description: "Create a new event on Google Calendar.",
    parameters: createEventSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);
      const tz = params.timezone ?? "UTC";

      const event: any = {
        summary: params.title,
        start: { dateTime: params.start_time, timeZone: tz },
        end: { dateTime: params.end_time, timeZone: tz },
      };

      if (params.description) event.description = params.description;
      if (params.location) event.location = params.location;
      if (params.attendees?.length) {
        event.attendees = params.attendees.map((email: string) => ({
          email,
        }));
      }

      const resp = await calendar.events.insert({
        calendarId: "primary",
        requestBody: event,
      });

      return {
        content: [
          {
            type: "text",
            text: `Event created: "${params.title}" (ID: ${resp.data.id})`,
          },
        ],
        details: undefined,
      };
    },
  };

  const update_event: AgentTool<typeof updateEventSchema> = {
    name: "update_event",
    label: "Update Calendar Event",
    description: "Update an existing Google Calendar event.",
    parameters: updateEventSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);

      const patch: any = {};
      if (params.title) patch.summary = params.title;
      if (params.description) patch.description = params.description;
      if (params.location) patch.location = params.location;
      if (params.start_time) {
        patch.start = { dateTime: params.start_time };
      }
      if (params.end_time) {
        patch.end = { dateTime: params.end_time };
      }

      await calendar.events.patch({
        calendarId: "primary",
        eventId: params.event_id,
        requestBody: patch,
      });

      return {
        content: [
          {
            type: "text",
            text: `Event updated: ${params.event_id}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const delete_event: AgentTool<typeof deleteEventSchema> = {
    name: "delete_event",
    label: "Delete Calendar Event",
    description: "Delete an event from Google Calendar.",
    parameters: deleteEventSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);

      await calendar.events.delete({
        calendarId: "primary",
        eventId: params.event_id,
      });

      return {
        content: [
          {
            type: "text",
            text: `Event deleted: ${params.event_id}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const get_calendar_details: AgentTool<typeof getCalendarSchema> = {
    name: "get_calendar_details",
    label: "Calendar Details",
    description: "Get details about the primary Google Calendar.",
    parameters: getCalendarSchema,
    execute: async () => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);

      const resp = await calendar.calendars.get({
        calendarId: "primary",
      });

      const cal = resp.data;

      return {
        content: [
          {
            type: "text",
            text: [
              `Calendar: ${cal.summary}`,
              `Timezone: ${cal.timeZone}`,
              `Description: ${cal.description ?? "(none)"}`,
            ].join("\n"),
          },
        ],
        details: undefined,
      };
    },
  };

  const get_event: AgentTool<typeof getEventSchema> = {
    name: "get_event",
    label: "Get Calendar Event",
    description: "Get details of a specific event by ID from Google Calendar.",
    parameters: getEventSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);
      const calendarId = params.calendar_id ?? "primary";

      const resp = await calendar.events.get({
        calendarId,
        eventId: params.event_id,
      });

      const e = resp.data;
      const start = (e.start as any)?.dateTime ?? (e.start as any)?.date ?? "?";
      const end = (e.end as any)?.dateTime ?? (e.end as any)?.date ?? "";
      const location = e.location ? `\nLocation: ${e.location}` : "";
      const attendees = (e.attendees ?? [])
        .map((a: any) => a.email)
        .join(", ");

      return {
        content: [
          {
            type: "text",
            text: [
              `Event: ${e.summary ?? "(No title)"}`,
              `ID: ${e.id}`,
              `Start: ${start}`,
              `End: ${end}`,
              location,
              e.description ? `Description: ${e.description}` : "",
              attendees ? `Attendees: ${attendees}` : "",
              `Status: ${e.status}`,
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: undefined,
      };
    },
  };

  const get_free_busy: AgentTool<typeof getFreeBusySchema> = {
    name: "get_free_busy",
    label: "Get Free/Busy",
    description: "Check free/busy status for calendar(s) in a time range.",
    parameters: getFreeBusySchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);
      const calendarIds = params.calendars ?? ["primary"];

      const resp = await calendar.freebusy.query({
        requestBody: {
          timeMin: params.time_min,
          timeMax: params.time_max,
          items: calendarIds.map((id) => ({ id })),
        },
      });

      const calendarsData = resp.data.calendars ?? {};
      const lines: string[] = [];

      for (const [calId, calData] of Object.entries(calendarsData)) {
        const busy = (calData as any).busy ?? [];
        if (busy.length === 0) {
          lines.push(`${calId}: Free during entire range`);
        } else {
          lines.push(`${calId}: ${busy.length} busy period(s)`);
          for (const period of busy) {
            lines.push(`  ${period.start} → ${period.end}`);
          }
        }
      }

      return {
        content: [
          { type: "text", text: lines.join("\n") || "No data available." },
        ],
        details: undefined,
      };
    },
  };

  const list_calendars: AgentTool<typeof listCalendarsSchema> = {
    name: "list_calendars",
    label: "List Calendars",
    description: "List all calendars accessible to the user.",
    parameters: listCalendarsSchema,
    execute: async () => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);

      const resp = await calendar.calendarList.list();
      const items = resp.data.items ?? [];

      if (items.length === 0) {
        return {
          content: [{ type: "text", text: "No calendars found." }],
          details: undefined,
        };
      }

      const lines = items.map((c: any) => {
        const primary = c.primary ? " (primary)" : "";
        return `- ${c.summary}${primary}\n  ID: ${c.id}\n  Access: ${c.accessRole}`;
      });

      return {
        content: [{ type: "text", text: lines.join("\n\n") }],
        details: undefined,
      };
    },
  };

  const quick_add: AgentTool<typeof quickAddSchema> = {
    name: "quick_add",
    label: "Quick Add Event",
    description:
      "Create an event using natural language (e.g., 'Meeting with John tomorrow at 3pm').",
    parameters: quickAddSchema,
    execute: async (_id, params) => {
      const credentials = getCredentials();
      const calendar = await getCalendarAPI(credentials);
      const calendarId = params.calendar_id ?? "primary";

      const resp = await calendar.events.quickAdd({
        calendarId,
        text: params.text,
      });

      return {
        content: [
          {
            type: "text",
            text: `Event created: "${resp.data.summary ?? params.text}" (ID: ${resp.data.id})`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [
    list_events,
    create_event,
    update_event,
    delete_event,
    get_calendar_details,
    get_event,
    get_free_busy,
    list_calendars,
    quick_add,
  ];
}
