'use strict';

(function () {
  var MainCtrl = function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds) {
    Feeds.setNewFeed();
    $scope.valid_feed = false;

    var throttled_updates = _.throttle(function () {
      Feeds.validateFeed($scope.feed).then(function (feed) {
        $scope.valid_feed = true;
        feed.feed_url = $rootScope.feed.feed_url;
        $rootScope.feed = feed;
      }).always(function () {
        jQuery('.loading-icon').hide();
      });
    }, 100);

    $scope.$watch('feed.feed_url', function () {
      $scope.valid_feed = false;
      if (!$scope.feed || !$scope.feed.feed_url) {
        return;
      }
      jQuery('.loading-icon').show();
      throttled_updates();
    });

    $scope.createFeed = function () {
      var button = jQuery('[data-save-btn]');
      button.attr("disabled", "disabled");
      button.html('<i class="icon-refresh icon-spin"></i>');
      Feeds.createFeed($rootScope.feed).then(function (feed) {
        jQuery('#newFeedModal').modal('hide');
        $location.path('/feed/' + feed.feed_type + '/' + feed.feed_id + '/').hash('settings');
      }, function () {
        window.alert('Something wen\'t wrong while saving your feed');
      }).always(function () {
        button.attr("disabled", null);
        button.html('Add Feed');
      });

      return false;
    };


  };

  MainCtrl.$inject = ['$rootScope', '$scope', 'LocalApiClient', '$routeParams', '$location', 'Feeds'];
  angular.module('pourOver').controller('MainCtrl', MainCtrl);
})();
