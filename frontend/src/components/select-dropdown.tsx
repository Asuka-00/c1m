import { useState } from 'react'
import { Loader } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FormControl } from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type SelectDropdownProps = {
  onValueChange?: (value: string) => void
  defaultValue: string | undefined
  placeholder?: string
  isPending?: boolean
  items: { label: string; value: string }[] | undefined
  disabled?: boolean
  className?: string
  isControlled?: boolean
}

/** 简单下拉选择（支持加载中状态与占位文本），用于 react-hook-form。 */
export function SelectDropdown({
  defaultValue,
  onValueChange,
  isPending,
  items,
  placeholder,
  disabled,
  className = '',
  isControlled = false,
}: SelectDropdownProps) {
  const [picked, setPicked] = useState(defaultValue)
  const current = isControlled ? defaultValue : picked
  const handleChange = (v: string) => {
    setPicked(v)
    onValueChange?.(v)
  }
  const defaultState = isControlled
    ? { value: defaultValue, onValueChange: handleChange }
    : { defaultValue, onValueChange: handleChange }
  return (
    <Select {...defaultState}>
      <FormControl>
        <SelectTrigger
          disabled={disabled}
          className={cn(className)}
          title={items?.find((i) => i.value === current)?.label}
        >
          <SelectValue placeholder={placeholder ?? 'Select'} />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        {isPending ? (
          <SelectItem disabled value='loading' className='h-14'>
            <div className='flex items-center justify-center gap-2'>
              <Loader className='h-5 w-5 animate-spin' />
              {'  '}
              Loading...
            </div>
          </SelectItem>
        ) : (
          items?.map(({ label, value }) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}
