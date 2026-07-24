import { useCallback, useEffect, useRef, useState } from 'react'

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

interface SpeechRecognitionErrorEventLike {
  error: string
}

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const scope = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

interface Options {
  onInterim?: (text: string) => void
  onFinal: (text: string) => void
  onError?: (message: string) => void
  disabled?: boolean
}

export function useSpeechToText({ onInterim, onFinal, onError, disabled }: Options) {
  const [listening, setListening] = useState(false)
  const [supported, setSupported] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const onInterimRef = useRef(onInterim)
  const onFinalRef = useRef(onFinal)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onInterimRef.current = onInterim
    onFinalRef.current = onFinal
    onErrorRef.current = onError
  }, [onFinal, onInterim, onError])

  useEffect(() => {
    setSupported(Boolean(getSpeechRecognition()))
  }, [])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const abort = useCallback(() => {
    recognitionRef.current?.abort()
    setListening(false)
  }, [])

  const start = useCallback(() => {
    if (disabled) return

    const SpeechRecognition = getSpeechRecognition()
    if (!SpeechRecognition) {
      onErrorRef.current?.('Voice input is not supported in this browser.')
      return
    }

    recognitionRef.current?.abort()

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.continuous = false
    recognition.interimResults = true

    recognition.onstart = () => setListening(true)
    recognition.onend = () => setListening(false)
    recognition.onerror = (event) => {
      setListening(false)
      if (event.error === 'aborted') return
      if (event.error === 'not-allowed') {
        onErrorRef.current?.('Microphone access was denied.')
        return
      }
      onErrorRef.current?.('Could not capture voice input. Please try again.')
    }
    recognition.onresult = (event) => {
      let previewFinal = ''
      let previewInterim = ''
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index]
        const transcript = result[0].transcript
        if (result.isFinal) previewFinal += transcript
        else previewInterim += transcript
      }

      const preview = `${previewFinal}${previewInterim}`.trim()
      if (preview) onInterimRef.current?.(preview)

      let newFinal = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        if (result.isFinal) newFinal += result[0].transcript
      }
      if (newFinal.trim()) onFinalRef.current(newFinal.trim())
    }

    recognitionRef.current = recognition
    recognition.start()
  }, [disabled])

  const toggle = useCallback(() => {
    if (listening) stop()
    else start()
  }, [listening, start, stop])

  useEffect(() => () => recognitionRef.current?.abort(), [])

  return { listening, supported, start, stop, toggle, abort }
}
