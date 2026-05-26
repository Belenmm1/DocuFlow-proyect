'use client'

import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { uploadDocument } from '@/lib/api'
import toast from 'react-hot-toast'
import type { Document } from '@/types'

interface Props {
  onUploaded?: (doc: Document) => void
}

type FileState = {
  file: File
  status: 'idle' | 'uploading' | 'done' | 'error'
  error?: string
  doc?: Document
}

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export default function Dropzone({ onUploaded }: Props) {
  const [files, setFiles] = useState<FileState[]>([])

  const upload = useCallback(async (fileState: FileState, index: number) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'uploading' } : f))
    try {
      const doc = await uploadDocument(fileState.file)
      setFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'done', doc } : f))
      toast.success(`${fileState.file.name} encolado para análisis`)
      onUploaded?.(doc)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Error al subir el archivo'
      setFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'error', error: msg } : f))
      toast.error(msg)
    }
  }, [onUploaded])

  const onDrop = useCallback((accepted: File[]) => {
    const newFiles: FileState[] = accepted.map(f => ({ file: f, status: 'idle' }))
    setFiles(prev => {
      const updated = [...prev, ...newFiles]
      newFiles.forEach((_, i) => {
        setTimeout(() => upload(newFiles[i], prev.length + i), i * 200)
      })
      return updated
    })
  }, [upload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: 100 * 1024 * 1024,
  })

  const remove = (i: number) => setFiles(prev => prev.filter((_, idx) => idx !== i))

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={clsx(
          'relative rounded-xl border-2 border-dashed px-8 py-10 text-center cursor-pointer transition-all duration-200',
          isDragActive
            ? 'border-[#00c2ff] bg-[rgba(0,194,255,0.06)] scale-[1.01]'
            : 'border-[#1e2d40] hover:border-[#2d4463] hover:bg-white/[0.02]'
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div className={clsx(
            'w-12 h-12 rounded-full flex items-center justify-center transition-all',
            isDragActive ? 'bg-[rgba(0,194,255,0.15)]' : 'bg-[#1e2d40]'
          )}>
            <Upload className={clsx('w-5 h-5', isDragActive ? 'text-[#00c2ff]' : 'text-[#5a7a96]')} />
          </div>
          <div>
            <p className="text-sm font-semibold text-[#c8d8ea]">
              {isDragActive ? 'Soltá acá' : 'Arrastrá archivos o hacé click'}
            </p>
            <p className="text-xs text-[#5a7a96] mt-1">PDF, DOCX, XLSX · Máx 100 MB</p>
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((f, i) => (
            <div key={i} className="df-card px-4 py-3 flex items-center gap-3">
              <FileText className="w-4 h-4 text-[#5a7a96] flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[#c8d8ea] truncate">{f.file.name}</p>
                <p className="text-xs text-[#5a7a96]">{formatBytes(f.file.size)}</p>
                {f.error && <p className="text-xs text-red-400 mt-0.5">{f.error}</p>}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {f.status === 'uploading' && <Loader2 className="w-4 h-4 text-[#00c2ff] animate-spin" />}
                {f.status === 'done' && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                {f.status === 'error' && <AlertCircle className="w-4 h-4 text-red-400" />}
                <button
                  onClick={() => remove(i)}
                  className="w-5 h-5 rounded flex items-center justify-center text-[#5a7a96] hover:text-red-400 hover:bg-red-400/10 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
