"use client";

import { useState, useRef, useEffect } from "react";
import Waveform from "@/components/waveform";
import Stats from "@/components/stats";
import { File, Upload } from "lucide-react";
import AudioSubmit from "@/components/audio-submit";

export default function TryIt() {
  const [file, setFile] = useState<File | undefined>();
  const [task, setTask] = useState<"transcribe" | "translate">("transcribe");
  const [language, setLanguage] = useState<string>("");
  const [targetLanguage, setTargetLanguage] = useState<string>("en");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [file]);

  return (
    <div className="container flex w-full flex-col items-center gap-12">
      <section className="text-center py-28 max-w-3xl flex flex-col gap-3 items-center w-full">
        <div className="text-5xl tracking-tighter font-semibold">
          Upload an audio file
        </div>
        {file && (
          <div className="flex flex-col items-center w-full gap-2">
            <h1 className="pt-12 font-semibold w-full">
              <Waveform file={file} />
            </h1>
            <AudioSubmit
              file={file}
              setFile={setFile}
              task={task}
              language={language.trim() || undefined}
              targetLanguage={task === "translate" ? targetLanguage : undefined}
            />
          </div>
        )}
        <div className="flex flex-col gap-3 items-center w-full max-w-md">
          <div className="flex items-center justify-center gap-3 w-full">
            <label className="text-sm text-gray-600 w-32 text-right">
              Mode
            </label>
            <select
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              value={task}
              onChange={(e) =>
                setTask(e.target.value as "transcribe" | "translate")
              }
            >
              <option value="transcribe">Transcribe</option>
              <option value="translate">Translate to English</option>
            </select>
          </div>
          <div className="flex items-center justify-center gap-3 w-full">
            <label className="text-sm text-gray-600 w-32 text-right">
              Language
            </label>
            <input
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              placeholder="auto (optional, e.g. en, fr, de)"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            />
          </div>
          {task === "translate" && (
            <div className="flex items-center justify-center gap-3 w-full">
              <label className="text-sm text-gray-600 w-32 text-right">
                Target
              </label>
              <input
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                placeholder="en"
                value={targetLanguage}
                onChange={(e) => setTargetLanguage(e.target.value)}
              />
            </div>
          )}
        </div>
        <div
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer justify-center"
        >
          {!file ? (
            <div className="my-5 flex gap-2 items-center px-2.5 py-1.5 rounded-lg border border-dashed border-gray-300 text-gray-600 bg-gray-100 bg-opacity-40">
              <Upload size={20} /> Select a File
            </div>
          ) : (
            <div className="my-5 flex gap-2 items-center px-2.5 py-1.5  rounded-lg border border-dashed border-gray-300 text-gray-600 bg-gray-100 bg-opacity-40">
              <File size={20} /> Change File
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg,.opus,.webm"
            style={{ display: "none" }}
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </div>
      </section>
      <Stats/>
    </div>
  );
}
