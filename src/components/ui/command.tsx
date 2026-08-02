import { cn } from '@/lib/utils'
import {
  Command as CommandPrimitive,
  CommandEmpty as CommandEmptyPrimitive,
  CommandGroup as CommandGroupPrimitive,
  CommandInput as CommandInputPrimitive,
  CommandItem as CommandItemPrimitive,
  CommandList as CommandListPrimitive,
  CommandSeparator as CommandSeparatorPrimitive,
  CommandLoading as CommandLoadingPrimitive,
} from 'cmdk'
import * as React from 'react'

const Command = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive>
>(({ className, ...props }, ref) => (
  <CommandPrimitive
    ref={ref}
    className={cn(
      'overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md',
      className,
    )}
    {...props}
  />
))
Command.displayName = 'Command'

const CommandInput = React.forwardRef<
  React.ElementRef<typeof CommandInputPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandInputPrimitive>
>(({ className, ...props }, ref) => (
  <div className="flex items-center border-b px-3" cmdk-input-wrapper="">
    <CommandInputPrimitive
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-md bg-secondary/40 py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  </div>
))
CommandInput.displayName = 'CommandInput'

const CommandList = React.forwardRef<
  React.ElementRef<typeof CommandListPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandListPrimitive>
>(({ className, ...props }, ref) => (
  <CommandListPrimitive
    ref={ref}
    className={cn('max-h-[300px] overflow-y-auto overflow-x-hidden', className)}
    {...props}
  />
))
CommandList.displayName = 'CommandList'

const CommandEmpty = React.forwardRef<
  React.ElementRef<typeof CommandEmptyPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandEmptyPrimitive>
>(({ className, ...props }, ref) => (
  <CommandEmptyPrimitive
    ref={ref}
    className={cn('py-6 text-center text-sm', className)}
    {...props}
  />
))
CommandEmpty.displayName = 'CommandEmpty'

const CommandGroup = React.forwardRef<
  React.ElementRef<typeof CommandGroupPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandGroupPrimitive>
>(({ className, ...props }, ref) => (
  <CommandGroupPrimitive
    ref={ref}
    className={cn(
      'overflow-hidden p-1 text-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground',
      className,
    )}
    {...props}
  />
))
CommandGroup.displayName = 'CommandGroup'

const CommandItem = React.forwardRef<
  React.ElementRef<typeof CommandItemPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandItemPrimitive>
>(({ className, ...props }, ref) => (
  <CommandItemPrimitive
    ref={ref}
    className={cn(
      'relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[disabled=true]:pointer-events-none data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground data-[disabled=true]:opacity-50',
      className,
    )}
    {...props}
  />
))
CommandItem.displayName = 'CommandItem'

const CommandSeparator = React.forwardRef<
  React.ElementRef<typeof CommandSeparatorPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandSeparatorPrimitive>
>(({ className, ...props }, ref) => (
  <CommandSeparatorPrimitive
    ref={ref}
    className={cn('-mx-1 h-px bg-border', className)}
    {...props}
  />
))
CommandSeparator.displayName = 'CommandSeparator'

const CommandLoading = React.forwardRef<
  React.ElementRef<typeof CommandLoadingPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandLoadingPrimitive>
>(({ className, ...props }, ref) => (
  <CommandLoadingPrimitive
    ref={ref}
    className={cn('py-6 text-center text-sm', className)}
    {...props}
  />
))
CommandLoading.displayName = 'CommandLoading'

export {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandLoading,
}