import { useCallback, useMemo, useState } from 'react';
import { logger } from '@/utils/logger';
import type { ScheduledTask } from '@/types';
import { RecurrenceType, TaskStatus } from '@/types';
import { Button, ConfirmDialog } from '@/components/ui';
import {
  Plus,
  CalendarClock,
  Loader2,
  Clock,
  Calendar,
  History,
  Play,
  Pause,
  Edit2,
  Trash2,
} from 'lucide-react';
import {
  useDeleteScheduledTaskMutation,
  useScheduledTasksQuery,
  useToggleScheduledTaskMutation,
} from '@/hooks/queries/useScheduling';
import { MAX_TASKS_LIMIT } from '@/config/constants';
import toast from 'react-hot-toast';
import { formatDistanceToNow } from 'date-fns';
import { formatLocalTimeFromUtc } from '@/utils/timezone';

interface TasksSettingsTabProps {
  onAddTask: () => void;
  onEditTask: (task: ScheduledTask) => void;
}

const getOrdinalSuffix = (day: number): string => {
  if (day === 1 || day === 21 || day === 31) return 'st';
  if (day === 2 || day === 22) return 'nd';
  if (day === 3 || day === 23) return 'rd';
  return 'th';
};

export const TasksSettingsTab: React.FC<TasksSettingsTabProps> = ({ onAddTask, onEditTask }) => {
  const { data: tasks, isLoading, error } = useScheduledTasksQuery();
  const [taskPendingDelete, setTaskPendingDelete] = useState<ScheduledTask | null>(null);
  const [togglingTaskId, setTogglingTaskId] = useState<string | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);

  const deleteTask = useDeleteScheduledTaskMutation();
  const toggleTask = useToggleScheduledTaskMutation();

  const tasksList = useMemo(() => tasks || [], [tasks]);
  const total = tasksList.length;
  const activeCount = useMemo(() => tasksList.filter((t) => t.enabled).length, [tasksList]);
  const isLimitReached = total >= MAX_TASKS_LIMIT;

  const handleToggleTask = useCallback(
    async (task: ScheduledTask) => {
      setTogglingTaskId(task.id);
      try {
        await toggleTask.mutateAsync(task.id);
      } catch (error) {
        logger.error('Failed to toggle task', 'TasksSettingsTab', error);
        toast.error('Failed to toggle task status');
      } finally {
        setTogglingTaskId(null);
      }
    },
    [toggleTask],
  );

  const handleDeleteRequest = useCallback((task: ScheduledTask) => {
    setTaskPendingDelete(task);
  }, []);

  const handleCloseDeleteDialog = useCallback(() => {
    setTaskPendingDelete(null);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!taskPendingDelete) return;
    const targetTask = taskPendingDelete;
    setDeletingTaskId(targetTask.id);
    try {
      await deleteTask.mutateAsync(targetTask.id);
      setTaskPendingDelete(null);
    } catch (error) {
      logger.error('Failed to delete task', 'TasksSettingsTab', error);
      toast.error('Failed to delete task');
    } finally {
      setDeletingTaskId(null);
    }
  }, [taskPendingDelete, deleteTask]);

  const getRecurrenceDisplay = (task: ScheduledTask) => {
    const timeLabel = formatLocalTimeFromUtc(task.scheduled_time);

    switch (task.recurrence_type) {
      case RecurrenceType.ONCE:
        return `Once at ${timeLabel}`;
      case RecurrenceType.DAILY:
        return `Daily at ${timeLabel}`;
      case RecurrenceType.WEEKLY: {
        const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
        const dayName =
          task.scheduled_day !== null && task.scheduled_day >= 0 && task.scheduled_day < days.length
            ? days[task.scheduled_day]
            : 'Unknown day';
        return `Every ${dayName} at ${timeLabel}`;
      }
      case RecurrenceType.MONTHLY: {
        if (task.scheduled_day == null) {
          return `Monthly at ${timeLabel}`;
        }
        const day = task.scheduled_day;
        const suffix = getOrdinalSuffix(day);
        return `Monthly on the ${day}${suffix} at ${timeLabel}`;
      }
      default:
        return 'Unknown';
    }
  };

  const getNextExecutionDisplay = (task: ScheduledTask) => {
    if (!task.next_execution) return 'Not scheduled';
    const nextDate = new Date(task.next_execution);
    const now = new Date();

    if (nextDate < now) {
      return 'Running now...';
    }

    const distance = formatDistanceToNow(nextDate, { addSuffix: true });
    return distance;
  };

  const getStatusBadge = (task: ScheduledTask) => {
    if (!task.enabled) {
      return (
        <span className="rounded-full bg-text-quaternary/10 px-2 py-1 text-xs text-text-secondary dark:bg-text-dark-quaternary/10 dark:text-text-dark-secondary">
          Paused
        </span>
      );
    }

    switch (task.status) {
      case TaskStatus.ACTIVE:
        return (
          <span className="rounded-full bg-success-100 px-2 py-1 text-xs text-success-700 dark:bg-success-900/30 dark:text-success-400">
            Active
          </span>
        );
      case TaskStatus.FAILED:
        return (
          <span className="rounded-full bg-error-100 px-2 py-1 text-xs text-error-700 dark:bg-error-900/30 dark:text-error-400">
            Failed
          </span>
        );
      case TaskStatus.COMPLETED:
        return (
          <span className="rounded-full bg-info-100 px-2 py-1 text-xs text-info-700 dark:bg-info-900/30 dark:text-info-400">
            Completed
          </span>
        );
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="mb-4">
            <h2 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
              Scheduled Tasks
            </h2>
          </div>
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-text-secondary dark:text-text-dark-secondary" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <div className="mb-4">
            <h2 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
              Scheduled Tasks
            </h2>
          </div>
          <div className="rounded-lg bg-error-50 p-4 text-error-600 dark:bg-error-900/20 dark:text-error-400">
            <p>Error loading tasks. Please try again.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <h2 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
            Scheduled Tasks
          </h2>
          <Button
            type="button"
            onClick={onAddTask}
            variant="outline"
            size="sm"
            className="flex w-full shrink-0 items-center justify-center gap-1.5 sm:w-auto"
            disabled={isLimitReached}
            title={isLimitReached ? `Maximum of ${MAX_TASKS_LIMIT} tasks reached` : undefined}
            aria-label="Add new scheduled task"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Task
          </Button>
        </div>

        <p className="mb-4 text-xs text-text-tertiary dark:text-text-dark-tertiary">
          Automate your workflows with scheduled AI tasks. Each task creates a new chat with your
          prompt at the specified time.
        </p>

        {tasksList.length === 0 ? (
          <div className="rounded-lg border border-border p-8 text-center dark:border-border-dark">
            <CalendarClock className="mx-auto mb-3 h-8 w-8 text-text-quaternary dark:text-text-dark-quaternary" />
            <p className="mb-3 text-sm text-text-tertiary dark:text-text-dark-tertiary">
              No scheduled tasks configured yet
            </p>
            <Button type="button" onClick={onAddTask} variant="primary" size="sm">
              Create Your First Task
            </Button>
          </div>
        ) : (
          <>
            {total > 0 && (
              <p className="mb-3 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                {total} / {MAX_TASKS_LIMIT} tasks • {activeCount} active
              </p>
            )}
            <div className="space-y-3">
              {tasksList.map((task) => (
                <div
                  key={task.id}
                  className="rounded-lg border border-border bg-surface p-4 transition-colors hover:border-border-hover dark:border-border-dark dark:bg-surface-dark dark:hover:border-border-dark-hover"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex items-center gap-2">
                        <h3 className="truncate text-sm font-medium text-text-primary dark:text-text-dark-primary">
                          {task.task_name}
                        </h3>
                        {getStatusBadge(task)}
                      </div>

                      <p className="mb-3 line-clamp-2 text-xs text-text-secondary dark:text-text-dark-secondary">
                        {task.prompt_message}
                      </p>

                      <div className="flex flex-wrap gap-4 text-xs text-text-secondary dark:text-text-dark-secondary">
                        <div className="flex items-center gap-1.5">
                          <Clock className="h-4 w-4" />
                          <span>{getRecurrenceDisplay(task)}</span>
                        </div>

                        {task.next_execution && task.enabled && (
                          <div className="flex items-center gap-1.5">
                            <Calendar className="h-4 w-4" />
                            <span>Next: {getNextExecutionDisplay(task)}</span>
                          </div>
                        )}

                        {task.execution_count > 0 && (
                          <div className="flex items-center gap-1.5">
                            <History className="h-4 w-4" />
                            <span>
                              Ran {task.execution_count} time{task.execution_count !== 1 ? 's' : ''}
                            </span>
                          </div>
                        )}
                      </div>

                      {task.last_error && (
                        <div className="mt-2 rounded bg-error-50 p-2 text-xs text-error-600 dark:bg-error-900/20 dark:text-error-400">
                          Error: {task.last_error}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleToggleTask(task)}
                        className="h-8 w-8 text-text-secondary dark:text-text-dark-secondary"
                        title={task.enabled ? 'Pause task' : 'Resume task'}
                        aria-label={task.enabled ? 'Pause task' : 'Resume task'}
                        disabled={togglingTaskId === task.id}
                      >
                        {togglingTaskId === task.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : task.enabled ? (
                          <Pause className="h-4 w-4" />
                        ) : (
                          <Play className="h-4 w-4" />
                        )}
                      </Button>

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => onEditTask(task)}
                        className="h-8 w-8 text-text-secondary dark:text-text-dark-secondary"
                        title="Edit task"
                        aria-label="Edit task"
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteRequest(task)}
                        className="h-8 w-8 text-error-600 hover:bg-error-50 dark:text-error-400 dark:hover:bg-error-400/10"
                        title="Delete task"
                        aria-label="Delete task"
                        disabled={deletingTaskId === task.id}
                      >
                        {deletingTaskId === task.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        isOpen={taskPendingDelete !== null}
        onClose={handleCloseDeleteDialog}
        onConfirm={handleConfirmDelete}
        title="Delete Task"
        message={`Are you sure you want to delete "${taskPendingDelete?.task_name ?? 'this task'}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
      />
    </div>
  );
};
