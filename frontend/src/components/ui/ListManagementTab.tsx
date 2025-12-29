import { ReactNode, useState } from 'react';
import { Button, ConfirmDialog } from '@/components/ui';
import { Plus, Loader2, LucideIcon, Edit2, Trash2 } from 'lucide-react';
import { logger } from '@/utils/logger';

interface ListManagementTabProps<T> {
  title: string;
  description: string;
  items: T[] | null;
  emptyIcon: LucideIcon;
  emptyText: string;
  emptyButtonText: string;
  addButtonText: string;
  deleteConfirmTitle: string;
  deleteConfirmMessage: (item: T) => string;
  getItemKey: (item: T, index: number) => string;
  onAdd: () => void;
  onEdit?: (index: number) => void;
  onDelete: (index: number) => void | Promise<void>;
  renderItem: (item: T, index: number) => ReactNode;
  maxLimit?: number;
  isMaxLimitReached?: boolean;
  footerContent?: ReactNode;
  logContext: string;
}

export const ListManagementTab = <T,>({
  title,
  description,
  items,
  emptyIcon: EmptyIcon,
  emptyText,
  emptyButtonText,
  addButtonText,
  deleteConfirmTitle,
  deleteConfirmMessage,
  getItemKey,
  onAdd,
  onEdit,
  onDelete,
  renderItem,
  maxLimit,
  isMaxLimitReached,
  footerContent,
  logContext,
}: ListManagementTabProps<T>) => {
  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null);

  const handleCloseDeleteDialog = () => {
    setPendingDeleteIndex(null);
  };

  const handleConfirmDelete = async () => {
    if (pendingDeleteIndex === null) return;
    setDeletingIndex(pendingDeleteIndex);
    try {
      await onDelete(pendingDeleteIndex);
      setPendingDeleteIndex(null);
    } catch (error) {
      logger.error(`Failed to delete item`, logContext, error);
    } finally {
      setDeletingIndex(null);
    }
  };

  const deleteTargetItem =
    pendingDeleteIndex !== null && items?.[pendingDeleteIndex] ? items[pendingDeleteIndex] : null;

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <h2 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
            {title}
          </h2>
          <Button
            type="button"
            onClick={onAdd}
            variant="outline"
            size="sm"
            className="flex w-full shrink-0 items-center justify-center gap-1.5 sm:w-auto"
            disabled={isMaxLimitReached}
            title={
              isMaxLimitReached && maxLimit ? `Maximum of ${maxLimit} items reached` : undefined
            }
          >
            <Plus className="h-3.5 w-3.5" />
            {addButtonText}
          </Button>
        </div>

        <p className="mb-4 text-xs text-text-tertiary dark:text-text-dark-tertiary">
          {description}
        </p>

        {!items || items.length === 0 ? (
          <div className="rounded-lg border border-border p-8 text-center dark:border-border-dark">
            <EmptyIcon className="mx-auto mb-3 h-8 w-8 text-text-quaternary dark:text-text-dark-quaternary" />
            <p className="mb-3 text-sm text-text-tertiary dark:text-text-dark-tertiary">
              {emptyText}
            </p>
            <Button type="button" onClick={onAdd} variant="primary" size="sm">
              {emptyButtonText}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item, index) => (
              <div
                key={getItemKey(item, index)}
                className="rounded-lg border border-border p-4 transition-colors hover:border-border-hover dark:border-border-dark dark:hover:border-border-dark-hover"
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">{renderItem(item, index)}</div>
                  <div className="ml-3 flex items-center gap-1">
                    {onEdit && (
                      <Button
                        type="button"
                        onClick={() => onEdit(index)}
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-text-tertiary hover:text-text-secondary dark:text-text-dark-tertiary dark:hover:text-text-dark-secondary"
                        aria-label="Edit item"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      type="button"
                      onClick={() => setPendingDeleteIndex(index)}
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-error-600 hover:bg-error-50 dark:text-error-400 dark:hover:bg-error-400/10"
                      aria-label="Delete item"
                      disabled={deletingIndex === index}
                    >
                      {deletingIndex === index ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {footerContent}
      </div>

      <ConfirmDialog
        isOpen={pendingDeleteIndex !== null}
        onClose={handleCloseDeleteDialog}
        onConfirm={handleConfirmDelete}
        title={deleteConfirmTitle}
        message={
          deleteTargetItem
            ? deleteConfirmMessage(deleteTargetItem)
            : 'Are you sure you want to delete this item? This action cannot be undone.'
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
      />
    </div>
  );
};
