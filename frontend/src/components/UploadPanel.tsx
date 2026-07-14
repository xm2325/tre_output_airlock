import { FileCheck2, UploadCloud } from 'lucide-react'
import { type DragEvent, useRef, useState } from 'react'
import type { OutputType, UploadMetadata } from '../types/api'

interface UploadPanelProps {
  busy: boolean
  onUpload: (file: File, metadata: UploadMetadata) => Promise<void>
}

const acceptedExtensions = ['csv', 'txt', 'pdf', 'png', 'jpg', 'jpeg']

export function UploadPanel({ busy, onUpload }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [projectCode, setProjectCode] = useState('UKB-DEMO-001')
  const [outputType, setOutputType] = useState<OutputType>('TABLE')
  const [outputDescription, setOutputDescription] = useState(
    'Synthetic aggregate analysis output prepared for controlled release.',
  )
  const [dragging, setDragging] = useState(false)

  function acceptFile(nextFile: File | undefined) {
    if (nextFile) setFile(nextFile)
  }

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    acceptFile(event.dataTransfer.files[0])
  }

  async function submit() {
    if (!file) return
    await onUpload(file, { projectCode, outputType, outputDescription })
    setFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const extension = file?.name.split('.').pop()?.toLowerCase()
  const extensionAllowed = !file || (extension ? acceptedExtensions.includes(extension) : false)
  const sizeAllowed = !file || file.size <= 5 * 1024 * 1024
  const metadataValid = projectCode.trim().length >= 2 && outputDescription.trim().length >= 10
  const ready = Boolean(file && extensionAllowed && sizeAllowed && metadataValid)

  return (
    <section className="panel upload-panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Researcher workflow</p>
          <h2>Submit an output package</h2>
        </div>
        <UploadCloud aria-hidden="true" />
      </div>

      <div className="form-grid form-grid--two">
        <label className="field-group">
          <span>Project code</span>
          <input value={projectCode} onChange={(event) => setProjectCode(event.target.value)} />
        </label>
        <label className="field-group">
          <span>Output type</span>
          <select value={outputType} onChange={(event) => setOutputType(event.target.value as OutputType)}>
            <option value="TABLE">Table</option>
            <option value="FIGURE">Figure</option>
            <option value="REPORT">Report</option>
            <option value="OTHER">Other</option>
          </select>
        </label>
      </div>
      <label className="field-group">
        <span>Purpose and release context</span>
        <textarea
          rows={3}
          value={outputDescription}
          onChange={(event) => setOutputDescription(event.target.value)}
        />
      </label>

      <label
        className={`drop-zone ${dragging ? 'drop-zone--active' : ''}`}
        htmlFor="output-file"
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <input
          ref={inputRef}
          id="output-file"
          type="file"
          accept=".csv,.txt,.pdf,.png,.jpg,.jpeg"
          onChange={(event) => acceptFile(event.target.files?.[0])}
        />
        <FileCheck2 aria-hidden="true" />
        <strong>{file ? file.name : 'Select or drop a synthetic output'}</strong>
        <span>CSV, TXT, PDF, PNG or JPEG · maximum 5 MB</span>
      </label>

      {file && (
        <div className="file-preflight">
          <div className={extensionAllowed ? 'preflight-ok' : 'preflight-error'}>
            <span /> File extension {extensionAllowed ? 'accepted' : 'not accepted'}
          </div>
          <div className={sizeAllowed ? 'preflight-ok' : 'preflight-error'}>
            <span /> {(file.size / 1024).toFixed(1)} KB {sizeAllowed ? 'within limit' : 'exceeds limit'}
          </div>
        </div>
      )}

      <button className="primary-button" disabled={!ready || busy} onClick={() => void submit()}>
        {busy ? 'Checking output…' : 'Submit to quarantine'}
      </button>
      <p className="fine-print">Synthetic portfolio demonstration only. Do not upload participant data.</p>
    </section>
  )
}
