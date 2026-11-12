import React, { useState, useRef } from 'react';
import { UploadCloud, Link as LinkIcon, AlertCircle, FileVideo, Check, Film, Sparkles } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import type { Project } from '../../types';
import { api } from '../../api/client';

export interface NewProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProjectCreated: (project: Project) => void;
}

export const NewProjectModal: React.FC<NewProjectModalProps> = ({
  isOpen,
  onClose,
  onProjectCreated,
}) => {
  const [activeTab, setActiveTab] = useState<'file' | 'url'>('file');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith('video/') || /\.(mp4|mkv|mov|webm|avi)$/i.test(file.name)) {
        setSelectedFile(file);
        setErrorMessage(null);
      } else {
        setErrorMessage('Por favor, selecione um arquivo de vídeo válido (MP4, MKV, MOV, WebM).');
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setErrorMessage(null);
    }
  };

  const handleSubmitFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMessage('Selecione um arquivo de vídeo para importar.');
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const newProj = await api.createProjectFromFile(selectedFile);
      onProjectCreated(newProj);
      handleClose();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Falha ao importar o arquivo.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmitUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUrl = url.trim();
    if (!cleanUrl) {
      setErrorMessage('Insira uma URL pública válida.');
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const newProj = await api.createProjectFromUrl(cleanUrl);
      onProjectCreated(newProj);
      handleClose();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Falha ao importar da URL.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setSelectedFile(null);
    setUrl('');
    setErrorMessage(null);
    setIsLoading(false);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Importar Vídeo para o Estúdio"
      subtitle="O vídeo será armazenado e processado 100% localmente no seu computador."
      maxWidth="580px"
    >
      <div>
        {/* Abas de Importação */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            marginBottom: '20px',
            borderBottom: '1px solid var(--border-subtle)',
            paddingBottom: '10px',
          }}
        >
          <button
            type="button"
            onClick={() => {
              setActiveTab('file');
              setErrorMessage(null);
            }}
            className={`btn btn-sm ${activeTab === 'file' ? 'btn-primary' : 'btn-ghost'}`}
          >
            <UploadCloud size={15} />
            Arquivo do Computador
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveTab('url');
              setErrorMessage(null);
            }}
            className={`btn btn-sm ${activeTab === 'url' ? 'btn-primary' : 'btn-ghost'}`}
          >
            <LinkIcon size={15} />
            Link / URL Pública
          </button>
        </div>

        {/* Mensagem de Erro */}
        {errorMessage && (
          <div
            style={{
              padding: '10px 14px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-md)',
              color: '#fca5a5',
              fontSize: '0.85rem',
              marginBottom: '18px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <AlertCircle size={16} color="var(--danger)" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Formulário: Upload Local */}
        {activeTab === 'file' && (
          <form onSubmit={handleSubmitFile}>
            <div
              tabIndex={0}
              role="button"
              aria-label="Selecionar arquivo de vídeo para importar"
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setIsDragging(false);
              }}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              style={{
                border: isDragging ? '2px dashed var(--primary)' : '2px dashed var(--border-strong)',
                backgroundColor: isDragging ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-input)',
                borderRadius: 'var(--radius-lg)',
                padding: '40px 20px',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                marginBottom: '20px',
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,.mp4,.mkv,.mov,.webm"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />

              <div
                style={{
                  width: '54px',
                  height: '54px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'rgba(244, 63, 94, 0.12)',
                  color: 'var(--primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 14px',
                }}
              >
                <UploadCloud size={26} />
              </div>

              {selectedFile ? (
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '1rem', marginBottom: '4px' }}>
                    {selectedFile.name}
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB • Clique para trocar de arquivo
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.98rem', marginBottom: '6px' }}>
                    Arraste o arquivo de vídeo aqui ou clique para selecionar
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Formatos suportados: MP4, MKV, MOV, WebM (Qualquer resolução)
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
                Cancelar
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={isLoading}
                disabled={!selectedFile || isLoading}
                icon={<Film size={16} />}
              >
                {isLoading ? 'Importando Mídia...' : 'Importar Vídeo'}
              </Button>
            </div>
          </form>
        )}

        {/* Formulário: URL Pública */}
        {activeTab === 'url' && (
          <form onSubmit={handleSubmitUrl}>
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label className="form-label">URL Pública do Vídeo</label>
              <input
                type="url"
                className="form-input"
                placeholder="https://exemplo.com/video.mp4 ou link suportado..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                autoFocus
              />
              <span className="form-hint">
                O backend do LocalClip fará o download da mídia diretamente para seu armazenamento local.
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
                Cancelar
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={isLoading}
                disabled={!url.trim() || isLoading}
                icon={<LinkIcon size={16} />}
              >
                {isLoading ? 'Baixando Vídeo...' : 'Importar da URL'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
};
