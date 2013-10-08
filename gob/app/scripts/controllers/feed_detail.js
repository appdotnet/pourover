'use strict';

angular.module('pourOver')
.controller('FeedDetailCtrl', ['$rootScope', '$scope', 'LocalApiClient', '$routeParams', '$location', 'Feeds', 'LocalUser', 'Channels', 'ApiClient', function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, LocalUser, Channels, RemoteApi) {

  $scope.schedule_periods = [
    {label: '1 mins', value: 1},
    {label: '5 mins', value: 5},
    {label: '15 mins', value: 15},
    {label: '30 mins', value: 30},
    {label: '60 mins', value: 60},
  ];

  $scope.feed_error = undefined;
  $scope.$watch('feed', function () {
    var preview_url = '/feed/preview';
    if($rootScope.feed.feed_id) {
      preview_url = '/feeds/' + $rootScope.feed.feed_type + '/' + $rootScope.feed.feed_id + '/preview';
    }

    if (!$rootScope.feed.feed_url) {
      return false;
    }
    jQuery('.loading-icon').show();
    ApiClient.get({
      url: preview_url,
      params: Feeds.serialize_feed($rootScope.feed)
    }).error(function () {
      jQuery('.loading-icon').hide();
    }).success(function (resp) {
      if (resp.status === 'ok') {
        $scope.posts = resp.data;
        $scope.feed_error = undefined;
      } else {
        $scope.posts = undefined;
        $scope.feed_error = resp.message;
      }
      jQuery('.loading-icon').hide();
    });
  }, true);

  Feeds.setFeed({
    feed_type: +$routeParams.feed_type,
    feed_id: +$routeParams.feed_id
  });

  var refreshEntries = function () {
    ApiClient.get({
      url: '/feeds/' + $rootScope.feed.feed_type + '/' + $rootScope.feed.feed_id + '/latest'
    }).success(function (resp) {
      if (resp.data && resp.data.entries) {
        var sorted_posts = _.groupBy(resp.data.entries, function (x) {
          return (x.overflow_reason) ? 'overflow' : 'published';
        });
        $scope.overflow_entries = sorted_posts.overflow;
        $scope.published_entries = sorted_posts.published;
      }
    });

    ApiClient.get({
      url: '/feeds/' + $rootScope.feed.feed_type + '/' + $rootScope.feed.feed_id + '/unpublished'
    }).success(function (resp) {
      if (resp.data && resp.data.entries) {
        $scope.unpublished_entries = resp.data.entries;
      }
    });
  };

  $scope.getChannelTitle = function (channel) {
    return RemoteApi.getChannelMetadata(channel).title;
  };

  $scope.publishEntry = function (entry) {
    ApiClient.post({
      url: '/feeds/' + $rootScope.feed.feed_type + '/' + $rootScope.feed.feed_id + '/entries/' + entry.id + '/publish'
    }).success(function () {
      refreshEntries();
    });
  };

  $scope.$watch('feed.feed_id', function () {
    if (!$rootScope.feed.feed_id) {
      return;
    }
    refreshEntries();
  });

  $scope.createOrUpdateFeed = function () {
    var button = jQuery('[data-save-btn]');
    var last_html = button.html();

    button.attr("disabled", "disabled");
    button.html('<i class="icon-refresh icon-spin"></i>');
    var finish = function () {
      button.attr("disabled", null);
      button.html(last_html);
    };

    var method = ($rootScope.feed.feed_id) ? 'updateFeed' : 'createFeed';
    Feeds[method]($rootScope.feed).then(finish, function () {
      finish();
      window.alert('Something wen\'t wrong while saving your feed');
    });

    return false;
  };

  $scope.deleteFeed = function () {
    var sure = window.confirm('Are you sure you want to delete this feed?');
    if (!sure) {
      return false;
    }
    var feed_type = $rootScope.feed.feed_type;
    var feed_id = $rootScope.feed.feed_id;
    Feeds.deleteFeed(feed_type, feed_id).then(function () {
      delete $scope.published_entries;
      delete $scope.unpublished_entries;
      $location.path('/');
    });

  };

  $scope.entryStatus = function (entry) {
    var status = 'Published';

    if (!entry.published) {
      status = 'Unpublished';
    }

    if (entry.overflow_reason) {
      status = entry.overflow_reason;
    }

    return status;
  };

  $scope.entryAction = function (entry) {
    var status = 'Republish Now';

    if (entry.published) {
      status = 'Republish Now';
    } else {
      status = 'Publish Now';
    }

    if (entry.overflow_reason) {
      status = 'Try Publishing Now';
    }

    return status;
  };

  $scope.showEmptyMessage = function () {
    var entry_lists = ['unpublished_entries', 'published_entries', 'overflow_entries'];
    entry_lists = _.filter(entry_lists, function (val) {
      var is_a_thing = $scope[val] && $scope[val].length;
      return (typeof(is_a_thing) !== 'undefined' && is_a_thing > 0) ? true : false;
    });
    return entry_lists.length === 0;
  };

  if ($location.hash() === 'settings') {
    jQuery('[data-target="#settings"]').tab('show');
  }
  jQuery('body').popover({
    selector: '[data-toggle="popover"]',
    trigger: 'hover'
  });
  //jQuery('[data-toggle="tooltip"]').tooltip();

}]);
