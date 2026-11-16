"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { parseVoiceCommand } = require("./voice_command_parser.js");

const now = new Date(2026, 10, 16, 9, 0, 0, 0);

test("creates a reminder and parses an explicit date and time", () => {
  const command = parseVoiceCommand("Remind me to call Sam tomorrow at 5 pm", { now });
  assert.equal(command.system, "reminders");
  assert.equal(command.action, "create");
  assert.equal(command.text, "call Sam");
  assert.equal(command.dueValue, "2026-11-17T17:00");
  assert.equal(command.needsTime, false);
});

test("understands polite spoken action requests without keeping the request words", () => {
  const reminder = parseVoiceCommand("Can you remind me to call Sam?", { now });
  assert.equal(reminder.action, "create");
  assert.equal(reminder.text, "call Sam");
  const mode = parseVoiceCommand("Could you please start rehearsal mode?", { now });
  assert.equal(mode.action, "activate");
  assert.equal(mode.modeKey, "rehearsal");
});

test("keeps numbers in a reminder title while extracting a later time", () => {
  const command = parseVoiceCommand("Remind me to take 2 pills at 5 pm tomorrow", { now });
  assert.equal(command.text, "take 2 pills");
  assert.equal(command.dueValue, "2026-11-17T17:00");
});

test("parses short relative reminder times", () => {
  const command = parseVoiceCommand("Remind me to call Sam in ten minutes", { now });
  assert.equal(command.text, "call Sam");
  assert.equal(command.dueValue, "2026-11-16T09:10");
  const later = parseVoiceCommand("Remind me to rehearse in three days", { now });
  assert.equal(later.text, "rehearse");
  assert.equal(later.dueValue, "2026-11-19T09:00");
});

test("asks for an exact time when speech only includes a date", () => {
  const command = parseVoiceCommand("Remind me to call Sam tomorrow", { now });
  assert.equal(command.text, "call Sam");
  assert.equal(command.needsTime, true);
  assert.equal(command.dueValue, "");
});

test("does not mistake a spoken ambiguous hour for reminder title text", () => {
  const command = parseVoiceCommand("Remind me to call Sam at five", { now });
  assert.equal(command.text, "call Sam");
  assert.equal(command.needsTime, true);
  assert.equal(command.dueValue, "");
});

test("understands spoken hour words when the time is explicit", () => {
  const command = parseVoiceCommand("Remind me to call Sam tomorrow at five pm", { now });
  assert.equal(command.text, "call Sam");
  assert.equal(command.dueValue, "2026-11-17T17:00");
});

test("distinguishes reminder list and completion actions", () => {
  assert.equal(parseVoiceCommand("Show my reminders").action, "list");
  const complete = parseVoiceCommand("Mark the task call Sam as done");
  assert.equal(complete.action, "complete");
  assert.equal(complete.text, "call Sam");
});

test("routes photo, file, and copy requests to the matching library action", () => {
  assert.equal(parseVoiceCommand("Choose photos").action, "photos");
  assert.equal(parseVoiceCommand("Open my files").action, "files");
  assert.equal(parseVoiceCommand("Copy my photos").action, "organize");
});

test("starts modes on explicit commands and opens app selection for social blocking", () => {
  const start = parseVoiceCommand("Start rehearsal mode");
  assert.equal(start.system, "home");
  assert.equal(start.action, "activate");
  assert.equal(start.modeKey, "rehearsal");
  const settings = parseVoiceCommand("Block social media", { selectedMode: "focus" });
  assert.equal(settings.action, "settings");
  assert.equal(settings.modeKey, "focus");
  assert.equal(parseVoiceCommand("Block Instagram", { selectedMode: "rehearsal" }).action, "settings");
  assert.equal(parseVoiceCommand("Stop mode", { system: "home", activeMode: "rest" }).modeKey, "rest");
});

test("routes natural reminder questions to the reminder list", () => {
  assert.equal(parseVoiceCommand("What reminders do I have?").action, "list");
  assert.equal(parseVoiceCommand("What reminders should I add?").system, "unknown");
});

test("supports common Swahili reminder and photo commands", () => {
  assert.equal(parseVoiceCommand("Nikumbushe kununua maziwa").text, "kununua maziwa");
  assert.equal(parseVoiceCommand("Onyesha vikumbusho").action, "list");
  assert.equal(parseVoiceCommand("Chagua picha").action, "photos");
});

test("does not turn questions or unmatched speech into reminders", () => {
  assert.equal(parseVoiceCommand("What time is it?").system, "unknown");
  assert.equal(parseVoiceCommand("How do I start focus mode?").system, "unknown");
  assert.equal(parseVoiceCommand("Hello there").system, "unknown");
});
