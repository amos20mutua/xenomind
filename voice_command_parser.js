"use strict";

(function installVoiceCommandParser(root, createParser) {
  const parser = createParser();
  if (typeof module === "object" && module.exports) {
    module.exports = parser;
  } else {
    root.XenomindVoiceCommands = parser;
  }
})(typeof globalThis === "object" ? globalThis : this, function createParser() {
  const WEEKDAYS = {
    sunday: 0,
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6
  };
  const NUMBER_WORDS = {
    one: 1, two: 2, three: 3, four: 4, five: 5, six: 6,
    seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
    fifteen: 15, twenty: 20, thirty: 30, forty: 40, sixty: 60
  };
  const SPOKEN_HOURS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve";

  function normalized(value) {
    return String(value || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase()
      .replace(/[’']/g, "")
      .replace(/[^\p{L}\p{N}:\s-]/gu, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function localDateTimeValue(date) {
    const pad = (part) => String(part).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function parseNumber(value) {
    return /^\d+$/.test(value) ? Number(value) : NUMBER_WORDS[value] || 0;
  }

  function parseVoiceSchedule(title, nowValue) {
    let cleaned = title;
    const now = nowValue instanceof Date ? new Date(nowValue) : new Date(nowValue || Date.now());
    const relative = cleaned.match(/\bin\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|sixty)\s+(minutes?|mins?|hours?|hrs?|days?|weeks?)\b/i);
    if (relative) {
      const amount = parseNumber(relative[1].toLowerCase());
      const unit = relative[2].toLowerCase();
      const multiplier = /^(?:week)/.test(unit) ? 10080
        : /^(?:day)/.test(unit) ? 1440
          : /^(?:hour|hr)/.test(unit) ? 60 : 1;
      const maximum = /^week/.test(unit) ? 52 : /^day/.test(unit) ? 365 : 10080;
      if (amount > 0 && amount <= maximum) {
        const due = new Date(now.getTime() + amount * multiplier * 60 * 1000);
        due.setSeconds(0, 0);
        cleaned = cleaned.replace(relative[0], " ").replace(/\s+/g, " ").trim();
        return { text: cleaned, dueValue: localDateTimeValue(due), needsTime: false };
      }
    }

    const datePattern = /\b(?:on\s+)?(today|tonight|tomorrow|(?:(?:next)\s+)?(?:sunday|monday|tuesday|wednesday|thursday|friday|saturday))(?:\s+(?:morning|afternoon|evening))?\b/i;
    const dateMatch = cleaned.match(datePattern);
    const timePattern = new RegExp(`\\b(?:(?:at|around|kwa)\\s+(\\d{1,2}|${SPOKEN_HOURS})(?::([0-5]\\d))?\\s*(am|pm)?|(\\d{1,2}):([0-5]\\d)\\s*(am|pm)?|(\\d{1,2}|${SPOKEN_HOURS})\\s*(am|pm))\\b`, "i");
    const timeMatch = cleaned.match(timePattern);
    let due = new Date(now);
    let datePhrase = dateMatch ? dateMatch[0] : "";
    let timePhrase = timeMatch ? timeMatch[0] : "";

    if (dateMatch) {
      const dateText = dateMatch[1].toLowerCase().replace(/^next\s+/, "");
      if (dateText === "tomorrow") {
        due.setDate(due.getDate() + 1);
      } else if (dateText === "today" || dateText === "tonight") {
        // Keep the current local calendar date.
      } else {
        const weekday = WEEKDAYS[dateText];
        const targetDistance = (weekday - due.getDay() + 7) % 7;
        due.setDate(due.getDate() + (targetDistance === 0 ? 7 : targetDistance));
      }
    }

    let hour = null;
    let minute = 0;
    if (timeMatch) {
      const hourText = timeMatch[1] || timeMatch[4] || timeMatch[7];
      const minuteText = timeMatch[2] || timeMatch[5] || "";
      hour = parseNumber(hourText.toLowerCase());
      minute = Number(minuteText || 0);
      const meridiem = (timeMatch[3] || timeMatch[6] || timeMatch[8] || "").toLowerCase();
      const hasMinutes = Boolean(minuteText);
      if (hour > 23 || (!meridiem && !hasMinutes)) hour = null;
      else if (meridiem && (hour < 1 || hour > 12)) hour = null;
      else if (meridiem === "pm" && hour < 12) hour += 12;
      else if (meridiem === "am" && hour === 12) hour = 0;
    }

    if (hour !== null) {
      due.setHours(hour, minute, 0, 0);
      if (!dateMatch && due.getTime() <= now.getTime()) due.setDate(due.getDate() + 1);
      cleaned = cleaned.replace(timePhrase, " ");
      if (dateMatch) cleaned = cleaned.replace(datePhrase, " ");
      cleaned = cleaned.replace(/\s+(?:by|before|on|at|around|kwa)$/i, "").replace(/\s+/g, " ").trim();
      if (due.getTime() > now.getTime()) {
        return { text: cleaned, dueValue: localDateTimeValue(due), needsTime: false };
      }
      return { text: cleaned, dueValue: "", needsTime: true };
    }

    if (timeMatch) {
      cleaned = cleaned.replace(timePhrase, " ");
      if (dateMatch) cleaned = cleaned.replace(datePhrase, " ");
      cleaned = cleaned.replace(/\s+(?:by|before|on|at|around|kwa)$/i, "").replace(/\s+/g, " ").trim();
      return { text: cleaned, dueValue: "", needsTime: true };
    }

    if (dateMatch) {
      cleaned = cleaned.replace(datePhrase, " ").replace(/\s+/g, " ").trim();
      cleaned = cleaned.replace(/\s+(?:by|before|on)$/i, "").trim();
      return { text: cleaned, dueValue: "", needsTime: true };
    }
    return { text: cleaned.trim(), dueValue: "", needsTime: false };
  }

  function cleanReminderTitle(value) {
    return String(value || "")
      .replace(/^\s*(?:please\s+)?(?:(?:could|can|would) you\s+(?:please\s+)?)?(?:i need to|i have to|need to|remind me to|remind me|remember to|remember|nikumbushe|kumbusha|add|create|make|set|schedule|ongeza|niweke)\s*/i, "")
      .replace(/^\s*(?:a\s+)?(?:reminder|task|to[- ]?do)(?:\s+(?:to|for))?\s*/i, "")
      .replace(/^\s*(?:me\s+)?to\s+/i, "")
      .replace(/\s+/g, " ")
      .replace(/[?.!,;:]+$/g, "")
      .trim();
  }

  function cleanCompletedTitle(value) {
    return String(value || "")
      .replace(/^\s*(?:please\s+)?(?:(?:could|can|would) you\s+(?:please\s+)?)?(?:check off|complete|finish|mark|done with|maliza|kamilisha)\s*/i, "")
      .replace(/^\s*(?:as\s+)?(?:complete|completed|done)\s*/i, "")
      .replace(/^\s*(?:the|this|my|a|an)\s+(?:reminder|task|to[- ]?do)\s*/i, "")
      .replace(/^\s*(?:reminder|task|to[- ]?do)\s*/i, "")
      .replace(/\s+(?:as\s+)?(?:complete|completed|done)$/i, "")
      .replace(/\s+/g, " ")
      .replace(/[?.!,;:]+$/g, "")
      .trim();
  }

  function cleanLibraryRequest(value) {
    return String(value || "")
      .replace(/^\s*(?:please\s+)?(?:(?:could|can|would) you\s+(?:please\s+)?)?(?:open|choose|select|find|browse|show|share|copy|organize|back up|backup|save|send|pick|chagua|fungua|nakili|hifadhi)\s*/i, "")
      .replace(/^\s*(?:my|the|a|an)\s+/, "")
      .replace(/\s+/g, " ")
      .replace(/[?.!,;:]+$/g, "")
      .trim();
  }

  function createReminderCommand(raw, context) {
    const schedule = parseVoiceSchedule(cleanReminderTitle(raw), context.now);
    if (!schedule.text) return null;
    return {
      system: "reminders",
      action: "create",
      text: schedule.text,
      dueValue: schedule.dueValue,
      needsTime: schedule.needsTime,
      modeKey: "",
      response: schedule.needsTime
        ? "I heard a reminder, but I need an exact date and time. Choose them under Schedule before sending."
        : schedule.dueValue
          ? "I heard a reminder with a due time. Review it, then tap Create reminder."
          : "I heard a reminder. Review the title, then tap Create reminder."
    };
  }

  function isLikelyReminderPhrase(words) {
    return /^(?:please\s+)?(?:i need to|i have to|need to|buy|call|pick up|pay|send|text|email|visit|meet|take|bring|check|book|order|practice|practise|prepare|finish|clean|write|read|review|submit|feed|water|remember to|piga|nunua|lipa|tuma|chukua|kumbuka|fanya|enda|tembelea|soma|andika|maliza|ongea|kagua)\b/.test(words);
  }

  function unknownCommand(raw, question) {
    return {
      system: "unknown",
      action: "clarify",
      text: raw,
      dueValue: "",
      needsTime: false,
      modeKey: "",
      response: question
        ? "I can route reminders, photos and files, and phone modes. I can't answer general questions yet."
        : "I couldn't match that to an action. Try ‘remind me to…’, ‘choose photos’, ‘open files’, or ‘start focus mode’."
    };
  }

  function parseVoiceCommand(transcript, context = {}) {
    const raw = String(transcript || "").trim();
    const words = normalized(raw);
    if (!words) return unknownCommand(raw, false);

    const system = context.system || "reminders";
    const isQuestion = /^(?:what|when|where|why|who|how|can you tell me|tell me|nini|lini|wapi|kwa nini|niambie)\b/.test(words)
      || /^(?:can|could|would|should)\s+(?:you|i)\b/.test(words);
    const politeActionRequest = /^(?:can|could|would) you\s+(?:please\s+)?(?:remind|remember|add|create|make|set|schedule|show|list|view|open|start|activate|enable|turn on|stop|end|disable|turn off|configure|choose|select|manage|block|lock|pause|find|complete|finish|check off|copy|organize|backup|back up|pick|share|chagua|fungua|onyesha|ongeza|washa|anzisha|zima|zuia)\b/.test(words);
    const explicitReminder = /\b(?:remind me|remember to|nikumbushe|kumbusha)\b/.test(words)
      || /\b(?:add|create|make|set|schedule|ongeza|niweke)\s+(?:a\s+)?(?:new\s+)?(?:reminder|task|to[- ]?do)\b/.test(words)
      || /\b(?:reminder|task|to[- ]?do)\s+(?:to|for)\b/.test(words);
    const reminderEntity = /\b(?:reminders?|tasks?|to[- ]?dos?|vikumbusho)\b/.test(words);
    const listVerb = /\b(?:show|list|view|open|find|what(?:s| is) on|display|onyesha|orodha)\b/.test(words);
    const asksAboutExistingReminders = /\bwhat\b/.test(words)
      && /\b(?:do i have|have i|are my|are there|is due|are due)\b/.test(words);
    const completeVerb = /\b(?:complete|finish|mark|check off|done with|maliza|kamilisha)\b/.test(words);

    if ((reminderEntity && (listVerb || asksAboutExistingReminders) && !completeVerb) || (system === "reminders" && /\b(?:show|list|view|open|onyesha|orodha)\s+(?:my\s+)?(?:reminders?|tasks?|vikumbusho)\b/.test(words))) {
      return { system: "reminders", action: "list", text: "", dueValue: "", needsTime: false, modeKey: "", response: "Opening your reminder list." };
    }

    if (isQuestion && !politeActionRequest) return unknownCommand(raw, true);

    if (completeVerb && (reminderEntity || explicitReminder || system === "reminders")) {
      const title = cleanCompletedTitle(raw);
      if (title && !/^(?:the\s+)?(?:reminders?|tasks?|vikumbusho)$/i.test(title)) {
        return { system: "reminders", action: "complete", text: title, dueValue: "", needsTime: false, modeKey: "", response: "I heard a request to complete a reminder. Review the matching item before confirming it." };
      }
    }

    if (explicitReminder) {
      const command = createReminderCommand(raw, context);
      if (command) return command;
    }

    const modeMatch = words.match(/\b(focus|concentrate|umakini|rehearsal|practice|practise|mazoezi|rest|sleep|bedtime|mapumziko)\b/);
    const modeKey = modeMatch
      ? /rehearsal|practice|practise|mazoezi/.test(modeMatch[1]) ? "rehearsal"
        : /rest|sleep|bedtime|mapumziko/.test(modeMatch[1]) ? "rest" : "focus"
      : context.selectedMode || "focus";
    const modeControl = /\b(?:start|activate|enable|turn on|switch on|begin|stop|end|disable|turn off|switch off|configure|set up|setup|choose|select|manage|block|lock|pause|washa|anzisha|zima|chagua|zuia)\b/.test(words);
    const socialTarget = /\b(?:social media|social apps?|apps? to block|block apps?|instagram|tiktok|facebook|whatsapp|snapchat|youtube|reddit|discord|twitter|x)\b/.test(words);
    const socialBlock = socialTarget && /\b(?:block|lock|pause|manage|configure|choose|select|zuia|chagua)\b/.test(words);
    const explicitMode = Boolean(modeMatch && (modeControl || /\bmode\b/.test(words) || system === "home"));
    if ((explicitMode || (system === "home" && (modeControl || modeMatch)) || socialBlock
      || (/\bmode\b/.test(words) && modeControl))) {
      const stop = /\b(?:stop|end|disable|turn off|switch off|zima)\b/.test(words);
      const configure = /\b(?:configure|set up|setup|choose|select|manage|block|lock|pause|chagua|zuia)\b/.test(words)
        && !/\b(?:start|activate|enable|turn on|switch on|begin|washa|anzisha)\b/.test(words);
      const start = /\b(?:start|activate|enable|turn on|switch on|begin|washa|anzisha)\b/.test(words);
      const action = stop ? "stop" : configure ? "settings" : start ? "activate" : "select";
      const actionModeKey = action === "stop" && !modeMatch ? context.activeMode || "" : modeKey;
      return {
        system: "home",
        action,
        text: "",
        dueValue: "",
        needsTime: false,
        modeKey: actionModeKey,
        response: action === "activate" ? `Starting ${actionModeKey} mode on this phone.`
          : action === "stop" ? `Ending ${actionModeKey || "active"} mode on this phone.`
            : action === "settings" ? `Opening ${actionModeKey} mode settings. Choose the apps you want blocked.`
              : `${actionModeKey[0].toUpperCase()}${actionModeKey.slice(1)} selected. Say ‘start ${actionModeKey} mode’ to activate it.`
      };
    }

    const photoNoun = /\b(?:photos?|pictures?|images?|camera roll|picha)\b/.test(words);
    const fileNoun = /\b(?:files?|documents?|downloads?|faili)\b/.test(words);
    const libraryVerb = /\b(?:open|choose|select|find|browse|show|share|copy|organize|back up|backup|save|send|pick|chagua|fungua|nakili|hifadhi)\b/.test(words);
    const isSingleLibraryChoice = /^(?:my\s+)?(?:photos?|pictures?|images?|files?|documents?|downloads?|picha|faili)$/.test(words);
    if ((photoNoun || fileNoun) && (libraryVerb || isSingleLibraryChoice || system === "library")) {
      const copying = /\b(?:copy|organize|back up|backup|save|nakili|hifadhi)\b/.test(words);
      const action = copying ? "organize" : fileNoun && !photoNoun ? "files" : "photos";
      return {
        system: "library",
        action,
        text: cleanLibraryRequest(raw),
        dueValue: "",
        needsTime: false,
        modeKey: "",
        response: action === "organize"
          ? "Opening the picker. Choose the items and destination before confirming the copy."
          : action === "files"
            ? "Opening the file picker. Choose the files you want to use."
            : "Opening the photo picker. Choose the photos you want to use."
      };
    }

    if (!isQuestion && system === "reminders" && words.split(" ").length <= 14
      && isLikelyReminderPhrase(words)) {
      const command = createReminderCommand(raw, context);
      if (command) return command;
    }
    if (isQuestion) return unknownCommand(raw, true);
    return unknownCommand(raw, false);
  }

  return { parseVoiceCommand, parseVoiceSchedule };
});
