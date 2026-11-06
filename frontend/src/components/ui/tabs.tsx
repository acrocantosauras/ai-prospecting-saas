'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface TabsContextValue {
  value: string;
  onValueChange: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs() {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error('useTabs must be used within Tabs');
  return ctx;
}

interface TabsListProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
}

function TabsList({
  className,
  defaultValue = '',
  value,
  onValueChange,
  children,
  ...props
}: TabsListProps) {
  const [internalValue, setInternalValue] = React.useState(defaultValue);
  const currentValue = value ?? internalValue;
  const handleChange = (v: string) => {
    onValueChange?.(v);
    setInternalValue(v);
  };

  // Tab panels must not render inside the tab bar: the bar is a short,
  // horizontally scrolling strip, so panel content placed inside it is
  // clipped and unreadable. Split triggers from panels while keeping both
  // inside the provider so panels can still read the active tab.
  const items = React.Children.toArray(children);
  const isTrigger = (child: React.ReactNode) =>
    React.isValidElement(child) && child.type === TabsTrigger;
  const triggers = items.filter(isTrigger);
  const panels = items.filter(child => !isTrigger(child));

  return (
    <TabsContext.Provider value={{ value: currentValue, onValueChange: handleChange }}>
      <div
        className={cn(
          'inline-flex max-w-full flex-wrap items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground',
          className,
        )}
        role="tablist"
        {...props}
      >
        {triggers}
      </div>
      {panels}
    </TabsContext.Provider>
  );
}

interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
  id?: string;
}

function TabsTrigger({ value, className, id, ...props }: TabsTriggerProps) {
  const { value: selected, onValueChange } = useTabs();
  const isActive = selected === value;

  return (
    <button
      id={id}
      role="tab"
      aria-selected={isActive}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        isActive
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
        className,
      )}
      onClick={() => onValueChange?.(value)}
      {...props}
    >
      {props.children}
    </button>
  );
}

interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

function TabsContent({ value, className, children, ...props }: TabsContentProps) {
  const { value: selected } = useTabs();
  if (selected !== value) return null;

  return (
    <div
      className={cn('mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2', className)}
      role="tabpanel"
      {...props}
    >
      {children}
    </div>
  );
}

export { TabsList, TabsTrigger, TabsContent, useTabs };
