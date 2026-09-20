# True Memory -- Full Pipeline Trace

Drives the real LangGraph pipeline end to end for one mock student: every turn below runs through the actual `retrieve_memories -> assess_completion -> chatbot -> ingest_memory` graph from `app/orchestration/graph.py`, not a simulation of it. The assistant's replies are genuine LLM output, so exact wording (and therefore what the encoding gate does with it) varies run to run.

Resetting test data for `user_id='00000000-0000-4000-8000-0000000000aa'`...

## Conversation

Each turn shows the user's message (with a note on what it's meant to demonstrate on the encoding gate), followed by Juno's real reply.

### Session 1 -- establishing facts

> 🙋 **User**
> Hey, I guess I'm here because I've been feeling really burnt out with school lately.
>
> _opening message -- store is empty, novelty should be maxed out_

> 🧠 **Juno**
> Hello! I’m Juno, an AI Therapist here to support you. I hear you’ve been feeling burnt out with school—that sounds tough. What name would you like me to call you?
>
> _script position after this turn: **Section 1**_

> 🙋 **User**
> Sam is fine, you can call me Sam.
>
> _script: answers the name question (Task 1b)_

> 🧠 **Juno**
> Nice to meet you, Sam. Do you have any questions about how this chat works or about me before we continue?
>
> _script position after this turn: **Section 1**_

> 🙋 **User**
> No, I don't have any questions. Let's get started.
>
> _script: no questions about the service (Task 1c) -- Section 1 should complete_

> 🧠 **Juno**
> How are you doing today, Sam?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I'm a junior majoring in computer science and this semester has just been brutal.
>
> _salient fact -- should encode_

> 🧠 **Juno**
> It sounds like the workload and demands of your junior year in computer science are feeling overwhelming right now. I’m sorry you’re going through such a tough stretch. How would you describe the way this stress is affecting you emotionally?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I'm taking five classes plus a part-time job at the campus library.
>
> _salient fact -- should encode_

> 🧠 **Juno**
> It sounds like you’re juggling a full course load with a part‑time job, which can be a lot to handle. How does that situation make you feel emotionally right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> lol yeah
>
> _noise -- should be skipped by the salience floor_

> 🧠 **Juno**
> I hear that it feels pretty intense right now. When you think about balancing those five classes and your job, what emotions come up for you?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> My roommate moved out last month and it's been way harder to focus without someone else around.
>
> _life event -- should encode_

> 🧠 **Juno**
> I hear that your roommate moving out has made it tougher to stay focused and perhaps left you feeling more alone. How does that change in your living situation affect your mood or motivation day‑to‑day?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I work at the library on weekends and it's honestly the only calm part of my week.
>
> _salient, establishes the job fact later sessions will build on_

> 🧠 **Juno**
> It sounds like your library shifts provide a rare sense of calm amid a busy schedule. When you’re not there, what emotions tend to come up for you?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> ok
>
> _noise -- should be skipped_

> 🧠 **Juno**
> I hear that your library shifts are a welcome calm, and without them things can feel a bit more chaotic. When you’re not at the library, what feelings tend to come up for you?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I'd rather talk through what's going on first, before any exercises.
>
> _script: picks 'explore my problem' over a CBT exercise (Task 2c) -- Section 2 should hand off to Section 3_

> 🧠 **Juno**
> I understand you’d like to talk more about what’s going on before we try any exercises. Would you prefer to keep exploring the challenges you’re facing right now, or would you like to jump straight into a CBT technique?
>
> _script position after this turn: **Section 2**_

---

### Session 2 -- a restatement, a marker-bypassed correction, more new facts

> 🙋 **User**
> I'm a junior majoring in computer science and this semester has just been brutal.
>
> _exact restatement of an existing memory -- novelty should be near zero, expect SKIP_

> 🧠 **Juno**
> Would you like to keep talking more about what’s been challenging for you right now, or would you prefer to try a CBT exercise at this point?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> Actually, I switched my major from computer science to data science last week.
>
> _contains an update marker ('switched') -- correction bypass should force ENCODE_

> 🧠 **Juno**
> I hear the recent switch from computer science to data science adds another layer of change on top of an already demanding semester. How are you feeling about that transition right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> thanks
>
> _noise -- should be skipped_

> 🧠 **Juno**
> I hear that switching from computer science to data science, your heavy course load, the part‑time job, and your roommate moving out are all adding up and feeling overwhelming. Would you like to continue exploring these challenges together, or would you prefer to try a CBT exercise right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I've been sleeping better since I started leaving my phone outside my room.
>
> _new, moderately salient -- likely encode_

> 🧠 **Juno**
> I’m glad to hear that leaving your phone outside has helped you sleep better. Would you prefer to keep talking through what’s been challenging for you right now, or would you like to try a CBT exercise?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> My best friend and I had a huge fight about a group project and we're barely speaking now.
>
> _new, salient, emotionally charged -- should encode_

> 🧠 **Juno**
> It sounds like the fight with your best friend over the group project is adding a lot of stress and leaving you feeling upset. Would you prefer to keep talking about what’s happening with that situation, or would you like to try a CBT exercise right now?
>
> _script position after this turn: **Section 2**_

---

### Session 3 -- a contradiction with no marker words (tests prediction error alone)

> 🙋 **User**
> I don't work at the library anymore, I'm tutoring freshman calc instead now.
>
> _contradicts the earlier library-job memory, but phrased so no marker matches ('no longer' / 'not anymore' aren't literally present) -- this is the real test of whether prediction error catches it unaided_

> 🧠 **Juno**
> It sounds like you’ve got a lot on your plate right now— the recent major change, a tough group‑project conflict with your best friend, and a new tutoring job. Would you like to keep exploring these challenges together, or would you prefer to try a CBT exercise right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> yeah
>
> _noise -- should be skipped_

> 🧠 **Juno**
> Great. Would you like to keep exploring what’s been going on for you, or would you prefer to start a CBT exercise right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I've been having panic moments again before exams, worse than last semester.
>
> _new, salient, relevant to the burnout thread -- should encode_

> 🧠 **Juno**
> I’m really sorry you’re dealing with those panic moments before exams, especially since they’re feeling even stronger than before. Would you like to keep talking about what’s happening and how it’s affecting you, or would you prefer to try a CBT exercise right now?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> sounds good
>
> _noise -- should be skipped_

> 🧠 **Juno**
> I’m really sorry you’ve been experiencing those panic moments before exams—they sound very distressing. Can you tell me more about what thoughts or sensations tend to come up for you when a panic episode starts?
>
> _script position after this turn: **Section 2**_

> 🙋 **User**
> I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project.
>
> _new, long, ties several earlier threads together -- should encode_

> 🧠 **Juno**
> I hear that the extra tutoring hours, the clash with your best friend, and the racing thoughts are keeping you up and adding to the stress. Could you tell me more about the main issue that’s weighing on you right now?
>
> _script position after this turn: **Section 3**_

---

## What the gate actually stored

Both roles run through the same encoding gate -- something Juno itself noticed out loud is as worth remembering as something the student said.

| Role | Gate score | Memory content |
|------|-----------|-----------------|
| user | 0.43 | Hey, I guess I'm here because I've been feeling really burnt out with school lately. |
| assistant | 0.55 | Hello! I’m Juno, an AI Therapist here to support you. I hear you’ve been feeling burnt out with school—that sounds tough. What name would you like me to call you? |
| user | 0.33 | Sam is fine, you can call me Sam. |
| assistant | 0.41 | Nice to meet you, Sam. Do you have any questions about how this chat works or about me before we continue? |
| user | 0.33 | No, I don't have any questions. Let's get started. |
| user | 0.44 | I'm a junior majoring in computer science and this semester has just been brutal. |
| assistant | 0.47 | It sounds like the workload and demands of your junior year in computer science are feeling overwhelming right now. I’m sorry you’re going through such a tough stretch. How would you describe the way this stress is affecting you emotionally? |
| assistant | 0.36 | It sounds like you’re juggling a full course load with a part‑time job, which can be a lot to handle. How does that situation make you feel emotionally right now? |
| assistant | 0.36 | I hear that it feels pretty intense right now. When you think about balancing those five classes and your job, what emotions come up for you? |
| user | 0.41 | My roommate moved out last month and it's been way harder to focus without someone else around. |
| assistant | 0.41 | I hear that your roommate moving out has made it tougher to stay focused and perhaps left you feeling more alone. How does that change in your living situation affect your mood or motivation day‑to‑day? |
| user | 0.31 | I work at the library on weekends and it's honestly the only calm part of my week. |
| assistant | 0.34 | It sounds like your library shifts provide a rare sense of calm amid a busy schedule. When you’re not there, what emotions tend to come up for you? |
| assistant | 0.30 | I hear that your library shifts are a welcome calm, and without them things can feel a bit more chaotic. When you’re not at the library, what feelings tend to come up for you? |
| user | 0.31 | I'd rather talk through what's going on first, before any exercises. |
| assistant | 0.49 | I understand you’d like to talk more about what’s going on before we try any exercises. Would you prefer to keep exploring the challenges you’re facing right now, or would you like to jump straight into a CBT technique? |
| assistant | 0.30 | Would you like to keep talking more about what’s been challenging for you right now, or would you prefer to try a CBT exercise at this point? |
| user | 0.28 | Actually, I switched my major from computer science to data science last week. |
| assistant | 0.40 | I hear the recent switch from computer science to data science adds another layer of change on top of an already demanding semester. How are you feeling about that transition right now? |
| assistant | 0.46 | I hear that switching from computer science to data science, your heavy course load, the part‑time job, and your roommate moving out are all adding up and feeling overwhelming. Would you like to continue exploring these challenges together, or would you prefer to try a CBT exercise right now? |
| user | 0.27 | I've been sleeping better since I started leaving my phone outside my room. |
| assistant | 0.35 | I’m glad to hear that leaving your phone outside has helped you sleep better. Would you prefer to keep talking through what’s been challenging for you right now, or would you like to try a CBT exercise? |
| user | 0.38 | My best friend and I had a huge fight about a group project and we're barely speaking now. |
| assistant | 0.46 | It sounds like the fight with your best friend over the group project is adding a lot of stress and leaving you feeling upset. Would you prefer to keep talking about what’s happening with that situation, or would you like to try a CBT exercise right now? |
| assistant | 0.37 | It sounds like you’ve got a lot on your plate right now— the recent major change, a tough group‑project conflict with your best friend, and a new tutoring job. Would you like to keep exploring these challenges together, or would you prefer to try a CBT exercise right now? |
| user | 0.35 | I've been having panic moments again before exams, worse than last semester. |
| assistant | 0.39 | I’m really sorry you’re dealing with those panic moments before exams, especially since they’re feeling even stronger than before. Would you like to keep talking about what’s happening and how it’s affecting you, or would you prefer to try a CBT exercise right now? |
| assistant | 0.35 | I’m really sorry you’ve been experiencing those panic moments before exams—they sound very distressing. Can you tell me more about what thoughts or sensations tend to come up for you when a panic episode starts? |
| user | 0.50 | I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project. |
| assistant | 0.41 | I hear that the extra tutoring hours, the clash with your best friend, and the racing thoughts are keeping you up and adding to the stress. Could you tell me more about the main issue that’s weighing on you right now? |

## Retrieval

Each query below is fused from two independent rankings -- full-text lexical search (L1) and pgvector cosine similarity (L2) -- via Reciprocal Rank Fusion (`RRF_K=60`, see `app/memory/episodic/retriever.py`). The RRF score is `sum(1 / (60 + rank))` across whichever list(s) a memory appeared in, so a memory both searches agree on outranks one that only tops a single list. This is the same `retrieve()` call `retrieve_memories` makes on every real chat turn -- these queries just make the result visible.

### Query: "What is the student studying?"

| Rank | RRF score | Retrieved memory |
|------|-----------|-------------------|
| 1 | 0.0164 | I'm a junior majoring in computer science and this semester has just been brutal. |
| 2 | 0.0161 | Actually, I switched my major from computer science to data science last week. |
| 3 | 0.0159 | I've been having panic moments again before exams, worse than last semester. |
| 4 | 0.0156 | Hey, I guess I'm here because I've been feeling really burnt out with school lately. |
| 5 | 0.0154 | I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project. |

### Query: "How is the part-time job going?"

| Rank | RRF score | Retrieved memory |
|------|-----------|-------------------|
| 1 | 0.0328 | I work at the library on weekends and it's honestly the only calm part of my week. |
| 2 | 0.0161 | I'd rather talk through what's going on first, before any exercises. |
| 3 | 0.0161 | I'm a junior majoring in computer science and this semester has just been brutal. |
| 4 | 0.0159 | Hey, I guess I'm here because I've been feeling really burnt out with school lately. |
| 5 | 0.0156 | I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project. |

### Query: "Tell me about the student's sleep problems."

| Rank | RRF score | Retrieved memory |
|------|-----------|-------------------|
| 1 | 0.0323 | I've been sleeping better since I started leaving my phone outside my room. |
| 2 | 0.0164 | I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project. |
| 3 | 0.0161 | I've been having panic moments again before exams, worse than last semester. |
| 4 | 0.0156 | I'm a junior majoring in computer science and this semester has just been brutal. |
| 5 | 0.0154 | Hey, I guess I'm here because I've been feeling really burnt out with school lately. |

### Query: "What's going on with the student's friendships?"

| Rank | RRF score | Retrieved memory |
|------|-----------|-------------------|
| 1 | 0.0164 | I'd rather talk through what's going on first, before any exercises. |
| 2 | 0.0164 | I'm a junior majoring in computer science and this semester has just been brutal. |
| 3 | 0.0161 | My best friend and I had a huge fight about a group project and we're barely speaking now. |
| 4 | 0.0159 | Hey, I guess I'm here because I've been feeling really burnt out with school lately. |
| 5 | 0.0156 | I've been having trouble falling asleep for the past three weeks, my mind just races about assignments, and I think it's tied to picking up more tutoring hours plus everything that happened with my best friend over that group project. |

## Try your own queries

_(interactive -- only meaningful when run in a terminal, not piped to a file; empty line to quit)_


query> 