import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import './glass-select.css';

export interface GlassSelectOption {
  value: number;
  label: string;
}

interface GlassSelectProps {
  id: string;
  label: string;
  value: number | '';
  options: GlassSelectOption[];
  placeholder: string;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export function GlassSelect({ id, label, value, options, placeholder, onChange, disabled = false }: GlassSelectProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const autoId = useId();
  const listId = `${id}-${autoId}-list`;
  const labelId = `${id}-${autoId}-label`;
  const selected = options.find(option => option.value === value);

  useEffect(() => {
    if (!open) return;
    listRef.current?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (open) listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  function openMenu() {
    if (disabled || options.length === 0) return;
    setActiveIndex(Math.max(0, options.findIndex(option => option.value === value)));
    setOpen(true);
  }

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onListKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(index => (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      setActiveIndex(event.key === 'Home' ? 0 : options.length - 1);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose(activeIndex);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const start = (activeIndex + 1) % options.length;
      const match = [...options.slice(start), ...options.slice(0, start)]
        .find(option => option.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()));
      if (match) setActiveIndex(options.findIndex(option => option.value === match.value));
    }
  }

  return (
    <div
      className="glass-select"
      ref={rootRef}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <label id={labelId} htmlFor={id} className="glass-select__label">{label}</label>
      <button
        id={id}
        ref={triggerRef}
        type="button"
        className="glass-select__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-labelledby={`${labelId} ${id}`}
        disabled={disabled}
        onClick={() => open ? setOpen(false) : openMenu()}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            openMenu();
          }
        }}
      >
        <span className={selected ? 'glass-select__value' : 'glass-select__placeholder'}>{selected?.label ?? placeholder}</span>
        <ChevronDown className={`glass-select__chevron${open ? ' glass-select__chevron--open' : ''}`} size={19} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={listId}
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          aria-labelledby={labelId}
          aria-activedescendant={`${listId}-option-${activeIndex}`}
          className="glass-select__menu focus-inset"
          onKeyDown={onListKeyDown}
        >
          {options.map((option, index) => (
            <div
              key={option.value}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={option.value === value}
              data-active={index === activeIndex}
              className="glass-select__option"
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(index)}
            >
              <span>{option.label}</span>
              {option.value === value && <Check size={17} aria-hidden="true" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
