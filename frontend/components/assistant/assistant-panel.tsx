"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Bot, CircleHelp, Send, Sparkles } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import ReactMarkdown from "react-markdown";
import { z } from "zod";
import { askAgent } from "@/lib/api";
import type { AgentAnswer } from "@/lib/types";
import { PageHeading } from "@/components/dashboard/page-heading";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const questionSchema = z.object({ query: z.string().trim().min(1, "Escribe una pregunta.").max(1200, "Máximo 1.200 caracteres.") });
type QuestionForm = z.infer<typeof questionSchema>;
type Message = { id: string; question: string; answer?: AgentAnswer; error?: string };
const suggestions = [
  "¿Qué estaciones tienen lecturas recientes de PM2.5?",
  "¿Qué anomalías espaciales se detectaron?",
  "¿Qué pronóstico está disponible para Itagüí?",
  "¿Hay datos suficientes para correlacionar lluvia y PM2.5?",
];

export function AssistantPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const form = useForm<QuestionForm>({ resolver: zodResolver(questionSchema), defaultValues: { query: "" } });
  const currentQuestion = useWatch({ control: form.control, name: "query" });
  const query = useMutation({ mutationFn: askAgent });
  const busy = query.isPending;

  function submit(values: QuestionForm) {
    const id = crypto.randomUUID();
    setMessages((current) => [...current, { id, question: values.query }]);
    query.mutate(values.query, {
      onSuccess: (answer) => setMessages((current) => current.map((message) => message.id === id ? { ...message, answer } : message)),
      onError: (error) => setMessages((current) => current.map((message) => message.id === id ? { ...message, error: error.message } : message)),
    });
    form.reset({ query: "" });
  }

  return <>
    <PageHeading eyebrow="AGENTE AMBIENTAL · DATOS VERIFICABLES" title="Pregunta a Jev" description="Jev consulta las herramientas y mediciones del backend. Si falta cobertura o un modelo, lo indica en lugar de completar la respuesta." />
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(270px,.7fr)]">
      <Card className="flex min-h-[620px] flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-full border border-[var(--line)]"><Bot className="size-4" /></span><div><p className="text-xs font-medium">Jev · inteligencia ambiental</p><p className="mt-1 text-[10px] text-[var(--muted)]">Herramientas de consulta SIATA</p></div></div><span className="flex items-center gap-1.5 text-[10px] text-[var(--muted)]"><span className="size-1.5 rounded-full bg-[var(--fg)]" />En línea</span></div>
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-5 sm:p-7" aria-live="polite">
          {!messages.length && <div className="m-auto max-w-md text-center"><Sparkles className="mx-auto size-5 text-[var(--muted)]" /><h2 className="mt-4 text-xl font-medium tracking-tight">Explora lo que publican las estaciones.</h2><p className="mt-2 text-xs leading-5 text-[var(--muted)]">Respuestas basadas en observaciones, métricas o modelos disponibles.</p></div>}
          {messages.map((message) => <div key={message.id} className="space-y-3">
            <div className="ml-auto max-w-[88%] rounded-2xl rounded-br-sm bg-[var(--surface-hover)] px-4 py-3 text-sm">{message.question}</div>
            {message.answer && <div className="max-w-[94%] rounded-2xl rounded-bl-sm border border-[var(--line)] px-4 py-4 text-sm leading-6"><div className="markdown-content"><ReactMarkdown>{message.answer.answer}</ReactMarkdown></div><Evidence answer={message.answer} /></div>}
            {message.error && <div className="max-w-[94%] rounded-xl border border-[var(--line)] px-4 py-3 text-xs text-[var(--muted)]" role="alert">No se pudo consultar Jev: {message.error}</div>}
            {!message.answer && !message.error && busy && messages.at(-1)?.id === message.id && <div className="flex items-center gap-2 text-xs text-[var(--muted)]" role="status"><span className="size-1.5 animate-pulse rounded-full bg-[var(--fg)]" />Consultando mediciones y herramientas…</div>}
          </div>)}
        </div>
        <form className="border-t border-[var(--line)] p-4 sm:p-5" onSubmit={form.handleSubmit(submit)}>
          <label className="sr-only" htmlFor="agent-question">Pregunta para Jev</label>
          <div className="flex gap-2"><Input id="agent-question" placeholder="Pregunta sobre estaciones, mediciones o modelos…" autoComplete="off" maxLength={1200} {...form.register("query")} /><Button size="icon" aria-label="Enviar pregunta" disabled={busy}><Send className="size-4" /></Button></div>
          <div className="mt-2 flex justify-between gap-2 text-[10px] text-[var(--muted)]"><span>{form.formState.errors.query?.message ?? "Hasta 1.200 caracteres · la respuesta no se transmite en streaming"}</span><span>{currentQuestion.length}/1200</span></div>
        </form>
      </Card>
      <aside className="space-y-4">
        <Card className="p-5"><p className="eyebrow">PREGUNTAS SUGERIDAS</p><div className="mt-3 divide-y divide-[var(--line)]">{suggestions.map((suggestion) => <button key={suggestion} type="button" className="group flex w-full items-center justify-between gap-3 py-3 text-left text-xs leading-5 text-[var(--muted)] hover:text-[var(--fg)]" onClick={() => { form.setValue("query", suggestion, { shouldValidate: true }); void form.handleSubmit(submit)(); }} disabled={busy}>{suggestion}<span aria-hidden="true" className="opacity-0 transition group-hover:opacity-100">↗</span></button>)}</div></Card>
        <Card className="p-5"><div className="flex items-center gap-2"><CircleHelp className="size-4 text-[var(--muted)]" /><p className="text-xs font-medium">Alcance de Jev</p></div><ul className="mt-3 space-y-2 text-[11px] leading-5 text-[var(--muted)]"><li>Consulta únicamente las funciones disponibles en el backend.</li><li>Cuando está configurado, NVIDIA NIM procesa explicaciones por API; no se descargan modelos ni se usa GPU local.</li><li>La pregunta y un resumen de evidencia se envían al proveedor remoto; no incluyas datos sensibles.</li><li>OpenRouter es una alternativa remota si NVIDIA no está configurado; sin claves, Jev usa un resumen determinista.</li><li>No conserva conversación después de recargar la página ni transmite respuestas en streaming.</li><li>Lluvia sin hora de observación no se interpreta como lluvia actual.</li></ul></Card>
      </aside>
    </div>
  </>;
}

function Evidence({ answer }: { answer: AgentAnswer }) {
  const evidence = answer.evidence;
  const provider = { nvidia_nim: "NVIDIA NIM API", openrouter: "OpenRouter API", local_evidence_summary: "resumen determinista", local_fallback: "resumen determinista (API no disponible)" }[answer.ai_provider ?? "local_evidence_summary"] ?? answer.ai_provider;
  return <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--line)] pt-3"><span className="rounded-full border border-[var(--line)] px-2 py-1 text-[9px] text-[var(--muted)]">{evidence.tool_calls_executed} herramientas · {evidence.execution_time_ms} ms</span>{evidence.stations.slice(0, 3).map((station) => <span key={station} className="rounded-full border border-[var(--line)] px-2 py-1 text-[9px] text-[var(--muted)]">{station}</span>)}{evidence.ml_models_applied.slice(0, 2).map((model) => <span key={model} className="rounded-full border border-[var(--line)] px-2 py-1 text-[9px] text-[var(--muted)]">{model}</span>)}<span className="rounded-full border border-[var(--line)] px-2 py-1 text-[9px] text-[var(--muted)]">{evidence.data_freshness}</span><span className="w-full text-[9px] text-[var(--muted)]">Proveedor de explicación: {provider}{answer.ai_model ? ` · ${answer.ai_model}` : ""}</span></div>;
}
